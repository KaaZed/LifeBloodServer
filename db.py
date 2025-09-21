# db.py — LifeBlood DB API bridge (PATCH-110)
import os
import math
import json
import asyncpg
from datetime import datetime, timezone, timedelta

from step_config import (
    STEP_LENGTH_METERS,
    CLUSTER_DISTANCE_METERS,
    EARTH_RADIUS_METERS,
    SPEED_MIN_KMH,
    SPEED_MAX_KMH,
    LBC_PER_STEP,
    REF_LBC_PER_STEP,
    SIGNUP_BONUS_LBC,
    DAILY_ENERGY_STEPS,
    GPS_MAX_ACCURACY_METERS,
    SMOOTHING_WINDOW_POINTS,
    MAX_JUMP_METERS,
    MIN_JUMP_INTERVAL_SEC,
)

DB_DSN = os.getenv("DB_DSN") or os.getenv("DATABASE_URL") or "postgresql://localhost:5432/lifeblood"


def _tz3_start_of_today_utc(now_utc: datetime | None = None):
    now_utc = now_utc or datetime.now(timezone.utc)
    tz3 = timezone(timedelta(hours=3))
    today_tz3 = now_utc.astimezone(tz3).date()
    start_tz3 = datetime.combine(today_tz3, datetime.min.time(), tz3)
    return start_tz3.astimezone(timezone.utc)


def _haversine_m(lat1, lon1, lat2, lon2):
    # быстро и без внешних либ
    R = EARTH_RADIUS_METERS
    p = math.pi/180.0
    dlat = (lat2-lat1)*p
    dlon = (lon2-lon1)*p
    a = (math.sin(dlat/2)**2 +
         math.cos(lat1*p)*math.cos(lat2*p)*math.sin(dlon/2)**2)
    return 2*R*math.asin(math.sqrt(a))


class LifeBloodDB:
    def __init__(self, dsn: str | None = None):
        self.dsn = dsn or DB_DSN
        self.pool: asyncpg.Pool | None = None

    async def connect(self):
        if not self.pool:
            self.pool = await asyncpg.create_pool(self.dsn, min_size=1, max_size=5)

    async def close(self):
        if self.pool:
            await self.pool.close()
            self.pool = None

    async def ensure_schema(self):
        await self.connect()
        async with self.pool.acquire() as c:
            # users
            await c.execute(f"""
            CREATE TABLE IF NOT EXISTS users (
              user_id            BIGINT PRIMARY KEY,
              username           TEXT,
              referrer_id        BIGINT,
              today_steps        INTEGER NOT NULL DEFAULT 0,
              total_steps        BIGINT  NOT NULL DEFAULT 0,
              today_lbc          NUMERIC(20,8) NOT NULL DEFAULT 0,
              total_lbc          NUMERIC(20,8) NOT NULL DEFAULT 0,
              energy_max         INTEGER NOT NULL DEFAULT 3000,
              energy_left        INTEGER NOT NULL DEFAULT 3000,
              dashboard_chat_id  BIGINT,
              dashboard_msg_id   BIGINT,
              reason_if_not_counted TEXT,
              created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
              updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            """)
            # безопасные ADD COLUMN IF NOT EXISTS (если таблица уже есть с не всеми полями)
            for col, ddl in [
              ("referrer_id",        "ALTER TABLE users ADD COLUMN IF NOT EXISTS referrer_id BIGINT"),
              ("today_steps",        "ALTER TABLE users ADD COLUMN IF NOT EXISTS today_steps INTEGER NOT NULL DEFAULT 0"),
              ("total_steps",        "ALTER TABLE users ADD COLUMN IF NOT EXISTS total_steps BIGINT NOT NULL DEFAULT 0"),
              ("today_lbc",          "ALTER TABLE users ADD COLUMN IF NOT EXISTS today_lbc NUMERIC(20,8) NOT NULL DEFAULT 0"),
              ("total_lbc",          "ALTER TABLE users ADD COLUMN IF NOT EXISTS total_lbc NUMERIC(20,8) NOT NULL DEFAULT 0"),
              ("energy_max",         f"ALTER TABLE users ADD COLUMN IF NOT EXISTS energy_max INTEGER NOT NULL DEFAULT {DAILY_ENERGY_STEPS}"),
              ("energy_left",        f"ALTER TABLE users ADD COLUMN IF NOT EXISTS energy_left INTEGER NOT NULL DEFAULT {DAILY_ENERGY_STEPS}"),
              ("energy_reset_at",    "ALTER TABLE users ADD COLUMN IF NOT EXISTS energy_reset_at TIMESTAMPTZ"),
              ("dashboard_chat_id",  "ALTER TABLE users ADD COLUMN IF NOT EXISTS dashboard_chat_id BIGINT"),
              ("dashboard_msg_id",   "ALTER TABLE users ADD COLUMN IF NOT EXISTS dashboard_msg_id BIGINT"),
              ("reason_if_not_counted","ALTER TABLE users ADD COLUMN IF NOT EXISTS reason_if_not_counted TEXT"),
              ("updated_at",         "ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now()"),
              ("created_at",         "ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now()"),
            ]:
                await c.execute(ddl + ";")

            await c.execute("""
                UPDATE users
                   SET energy_reset_at = COALESCE(energy_reset_at, updated_at, created_at, now())
                 WHERE energy_reset_at IS NULL
            """)

            # точки гео
            await c.execute("""
            CREATE TABLE IF NOT EXISTS locations (
              id        BIGSERIAL PRIMARY KEY,
              user_id   BIGINT NOT NULL,
              ts        TIMESTAMPTZ NOT NULL,
              lat       DOUBLE PRECISION NOT NULL,
              lon       DOUBLE PRECISION NOT NULL,
              accuracy  DOUBLE PRECISION,
              heading   INTEGER,
              created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            CREATE INDEX IF NOT EXISTS idx_locations_user_ts ON locations(user_id, ts DESC);
            """)

            # состояние «пятна» (кластер)
            await c.execute("""
            CREATE TABLE IF NOT EXISTS user_state (
              user_id     BIGINT PRIMARY KEY,
              cluster_lat DOUBLE PRECISION,
              cluster_lon DOUBLE PRECISION,
              last_lat    DOUBLE PRECISION,
              last_lon    DOUBLE PRECISION,
              last_ts     TIMESTAMPTZ,
              residual_m  DOUBLE PRECISION,
              cluster_start_ts TIMESTAMPTZ,
              segment_start_ts TIMESTAMPTZ,
              recent_points JSONB
            );
            """)
            for ddl in [
                "ALTER TABLE user_state ADD COLUMN IF NOT EXISTS cluster_start_ts TIMESTAMPTZ",
                "ALTER TABLE user_state ADD COLUMN IF NOT EXISTS last_lat DOUBLE PRECISION",
                "ALTER TABLE user_state ADD COLUMN IF NOT EXISTS last_lon DOUBLE PRECISION",
                "ALTER TABLE user_state ADD COLUMN IF NOT EXISTS residual_m DOUBLE PRECISION",
                "ALTER TABLE user_state ADD COLUMN IF NOT EXISTS segment_start_ts TIMESTAMPTZ",
                "ALTER TABLE user_state ADD COLUMN IF NOT EXISTS recent_points JSONB",
            ]:
                await c.execute(ddl + ";")

    # === служебные ===
    async def _ensure_user(self, user_id: int, username: str | None):
        await self.connect()
        async with self.pool.acquire() as c:
            row = await c.fetchrow("SELECT user_id FROM users WHERE user_id=$1", user_id)
            if row:
                await c.execute("UPDATE users SET username=$2, updated_at=now() WHERE user_id=$1", user_id, username)
                return False
            await c.execute("""
                INSERT INTO users (user_id, username, energy_max, energy_left, energy_reset_at)
                VALUES ($1, $2, $3, $3, now())
            """, user_id, username, DAILY_ENERGY_STEPS)
            return True

    # === публичный API, которого ждёт webhook_app ===
    async def register_user(self, user_id: int, username: str | None, referrer_id: int | None = None):
        """Единичная регистрация + реф.бонус."""
        is_new = await self._ensure_user(user_id, username)
        async with self.pool.acquire() as c:
            if is_new:
                # сохранить реферала (не сам на себя)
                ref = None
                if referrer_id and referrer_id != user_id:
                    ref = referrer_id
                await c.execute("UPDATE users SET referrer_id=$2, updated_at=now() WHERE user_id=$1", user_id, ref)

                # бонусы по 25 LBC
                await c.execute("UPDATE users SET total_lbc = COALESCE(total_lbc,0) + $2 WHERE user_id=$1", user_id, SIGNUP_BONUS_LBC)
                if ref:
                    await c.execute("UPDATE users SET total_lbc = COALESCE(total_lbc,0) + $2 WHERE user_id=$1", ref, SIGNUP_BONUS_LBC)
            # если не новый — просто актуализируем username
            else:
                await c.execute("UPDATE users SET username=$2, updated_at=now() WHERE user_id=$1", user_id, username)

    async def stats(self, user_id: int) -> dict:
        """Минимально нужная статистика для дашборда."""
        await self._maybe_daily_reset(user_id)
        await self.connect()
        async with self.pool.acquire() as c:
            row = await c.fetchrow("""
                SELECT user_id, username,
                       today_steps, total_steps,
                       today_lbc, total_lbc,
                       energy_left, energy_max,
                       reason_if_not_counted,
                       dashboard_chat_id, dashboard_msg_id
                  FROM users
                 WHERE user_id=$1
            """, user_id)
            if not row:
                # пользователь ещё не создан — вернём нули
                return {
                    "user_id": user_id, "username": None,
                    "today_steps": 0, "total_steps": 0,
                    "today_lbc": 0, "total_lbc": 0,
                    "energy_left": DAILY_ENERGY_STEPS, "energy_max": DAILY_ENERGY_STEPS,
                    "dashboard_chat_id": None, "dashboard_msg_id": None,
                }
            return dict(row)

    async def get_dashboard_target(self, user_id: int):
        """Куда редактировать дашборд (chat_id, msg_id) или (None, None)."""
        await self.connect()
        async with self.pool.acquire() as c:
            row = await c.fetchrow("SELECT dashboard_chat_id, dashboard_msg_id FROM users WHERE user_id=$1", user_id)
            if not row: return (None, None)
            return (row["dashboard_chat_id"], row["dashboard_msg_id"])

    async def save_dashboard_msg_id(self, user_id: int, chat_id: int, msg_id: int):
        await self.connect()
        async with self.pool.acquire() as c:
            await c.execute("""
                UPDATE users
                   SET dashboard_chat_id=$2, dashboard_msg_id=$3, updated_at=now()
                 WHERE user_id=$1
            """, user_id, chat_id, msg_id)

    async def _maybe_daily_reset(self, user_id: int):
        """Сбросить суточные поля, если наступил новый день по UTC+3."""
        await self.connect()
        start_utc = _tz3_start_of_today_utc()
        async with self.pool.acquire() as c:
            await c.execute("""
                UPDATE users
                   SET today_steps=0,
                       today_lbc=0,
                       energy_left=energy_max,
                       energy_reset_at=now(),
                       updated_at=now()
                 WHERE user_id=$1
                   AND (energy_reset_at IS NULL OR energy_reset_at < $2)
            """, user_id, start_utc)

    async def process_location(
        self,
        user_id: int,
        username: str | None,
        *,
        ts: int | float | None,
        lat: float,
        lon: float,
        accuracy: float | None = None,
        heading: int | None = None,
        live_period: int | None = None,
        chat_id: int | None = None
    ) -> dict:
        """Принимает live-location. Считает шаги сегментами по 100 м с накоплением остатка."""
        await self._ensure_user(user_id, username)
        await self._maybe_daily_reset(user_id)
        await self.connect()

        # ts -> datetime
        t = datetime.fromtimestamp(float(ts), tz=timezone.utc) if ts is not None else datetime.now(tz=timezone.utc)

        acc_val: float | None
        try:
            acc_val = float(accuracy) if accuracy is not None else None
        except (TypeError, ValueError):
            acc_val = None

        async with self.pool.acquire() as c, c.transaction():
            # Сохраним точку
            await c.execute("""
                INSERT INTO locations (user_id, ts, lat, lon, accuracy, heading)
                VALUES ($1,$2,$3,$4,$5,$6)
            """, user_id, t, lat, lon, accuracy, heading)

            # Текущее состояние сегмента
            st = await c.fetchrow(
                """
                SELECT cluster_lat, cluster_lon, last_lat, last_lon, last_ts,
                       residual_m, cluster_start_ts, segment_start_ts, recent_points
                  FROM user_state
                 WHERE user_id=$1
                """,
                user_id,
            )
            # --- окно сглаживания (anti-jitter)
            recent_points_prev: list[dict] = []
            if st and st.get("recent_points"):
                rp_raw = st["recent_points"]
                if isinstance(rp_raw, str):
                    try:
                        rp_raw = json.loads(rp_raw)
                    except json.JSONDecodeError:
                        rp_raw = []
                if isinstance(rp_raw, list):
                    for item in rp_raw:
                        if not isinstance(item, dict):
                            continue
                        try:
                            lat_v = float(item.get("lat"))
                            lon_v = float(item.get("lon"))
                            ts_raw = item.get("ts")
                            ts_v = float(ts_raw) if ts_raw is not None else None
                        except (TypeError, ValueError):
                            continue
                        recent_points_prev.append({"lat": lat_v, "lon": lon_v, "ts": ts_v})

            point_ts = float(t.timestamp())
            new_point = {"lat": float(lat), "lon": float(lon), "ts": point_ts}
            reset_lat = new_point["lat"]
            reset_lon = new_point["lon"]
            recent_points_updated = recent_points_prev + [new_point]
            if len(recent_points_updated) > SMOOTHING_WINDOW_POINTS:
                recent_points_updated = recent_points_updated[-SMOOTHING_WINDOW_POINTS:]
            smoothed_lat = sum(p["lat"] for p in recent_points_updated) / len(recent_points_updated)
            smoothed_lon = sum(p["lon"] for p in recent_points_updated) / len(recent_points_updated)
            prev_window = recent_points_updated[:-1]
            last_lat_prev = st["last_lat"] if st and st["last_lat"] is not None else None
            last_lon_prev = st["last_lon"] if st and st["last_lon"] is not None else None
            if last_lat_prev is None or last_lon_prev is None:
                if prev_window:
                    last_lat_prev = sum(p["lat"] for p in prev_window) / len(prev_window)
                    last_lon_prev = sum(p["lon"] for p in prev_window) / len(prev_window)
                else:
                    last_lat_prev = smoothed_lat
                    last_lon_prev = smoothed_lon
            recent_points_json = json.dumps(recent_points_updated, ensure_ascii=False)
            single_point_json = json.dumps([new_point], ensure_ascii=False)

            if not st or st["last_lat"] is None or st["last_lon"] is None:
                # Инициализация сегмента
                await c.execute(
                    """
                    INSERT INTO user_state (
                        user_id, cluster_lat, cluster_lon,
                        last_lat, last_lon, last_ts,
                        residual_m, cluster_start_ts, segment_start_ts,
                        recent_points
                    )
                    VALUES ($1,$2,$3,$2,$3,$4,0,$4,$4,$5)
                    ON CONFLICT (user_id) DO UPDATE
                    SET cluster_lat=EXCLUDED.cluster_lat,
                        cluster_lon=EXCLUDED.cluster_lon,
                        last_lat=EXCLUDED.last_lat,
                        last_lon=EXCLUDED.last_lon,
                        last_ts=EXCLUDED.last_ts,
                        residual_m=0,
                        cluster_start_ts=EXCLUDED.cluster_start_ts,
                        segment_start_ts=EXCLUDED.segment_start_ts,
                        recent_points=EXCLUDED.recent_points
                    """,
                    user_id,
                    reset_lat,
                    reset_lon,
                    t,
                    single_point_json,
                )
                await c.execute(
                    "UPDATE users SET reason_if_not_counted=$2, updated_at=now() WHERE user_id=$1",
                    user_id,
                    "segment_init",
                )
                return {"counted": 0, "reason": "segment_init"}

            if acc_val is not None and acc_val > GPS_MAX_ACCURACY_METERS:
                await c.execute(
                    """
                    UPDATE user_state
                       SET cluster_lat=$2,
                           cluster_lon=$3,
                           last_lat=$2,
                           last_lon=$3,
                           last_ts=$4,
                           residual_m=0,
                           cluster_start_ts=$4,
                           segment_start_ts=$4,
                           recent_points=$5
                     WHERE user_id=$1
                    """,
                    user_id,
                    reset_lat,
                    reset_lon,
                    t,
                    single_point_json,
                )
                await c.execute(
                    "UPDATE users SET reason_if_not_counted=$2, updated_at=now() WHERE user_id=$1",
                    user_id,
                    f"gps_accuracy:{acc_val:.1f}m",
                )
                return {"counted": 0, "reason": "gps_accuracy", "accuracy": acc_val}

            last_lat = last_lat_prev if last_lat_prev is not None else st["cluster_lat"]
            last_lon = last_lon_prev if last_lon_prev is not None else st["cluster_lon"]
            seg_start_ts = (
                st["segment_start_ts"]
                or st["cluster_start_ts"]
                or st["last_ts"]
                or t
            )
            residual_prev = float(st["residual_m"] or 0.0)
            last_ts_prev = st["last_ts"] if st else None

            if last_lat is None or last_lon is None:
                # fallback safety: реинициализация
                await c.execute(
                    """
                    UPDATE user_state
                       SET cluster_lat=$2,
                           cluster_lon=$3,
                           last_lat=$2,
                           last_lon=$3,
                           last_ts=$4,
                           residual_m=0,
                           cluster_start_ts=$4,
                           segment_start_ts=$4,
                           recent_points=$5
                     WHERE user_id=$1
                    """,
                    user_id,
                    reset_lat,
                    reset_lon,
                    t,
                    single_point_json,
                )
                await c.execute(
                    "UPDATE users SET reason_if_not_counted=$2, updated_at=now() WHERE user_id=$1",
                    user_id,
                    "segment_reinit",
                )
                return {"counted": 0, "reason": "segment_reinit"}

            segment_dist = _haversine_m(last_lat, last_lon, smoothed_lat, smoothed_lon)
            dt_since_last = None
            if last_ts_prev:
                try:
                    dt_since_last = abs((t - last_ts_prev).total_seconds())
                except Exception:
                    dt_since_last = None
            if (
                dt_since_last is not None
                and dt_since_last < float(MIN_JUMP_INTERVAL_SEC)
                and segment_dist > MAX_JUMP_METERS
            ):
                await c.execute(
                    """
                    UPDATE user_state
                       SET cluster_lat=$2,
                           cluster_lon=$3,
                           last_lat=$2,
                           last_lon=$3,
                           last_ts=$4,
                           residual_m=0,
                           cluster_start_ts=$4,
                           segment_start_ts=$4,
                           recent_points=$5
                     WHERE user_id=$1
                    """,
                    user_id,
                    reset_lat,
                    reset_lon,
                    t,
                    single_point_json,
                )
                await c.execute(
                    "UPDATE users SET reason_if_not_counted=$2, updated_at=now() WHERE user_id=$1",
                    user_id,
                    "jump",
                )
                return {
                    "counted": 0,
                    "reason": "jump",
                    "jump_m": segment_dist,
                    "jump_dt": dt_since_last,
                }
            total_m = residual_prev + segment_dist

            if total_m < CLUSTER_DISTANCE_METERS:
                cluster_lat = st["cluster_lat"] if st["cluster_lat"] is not None else last_lat
                cluster_lon = st["cluster_lon"] if st["cluster_lon"] is not None else last_lon
                await c.execute(
                    """
                    UPDATE user_state
                       SET last_lat=$2,
                           last_lon=$3,
                           last_ts=$4,
                           residual_m=$5,
                           cluster_lat=COALESCE(cluster_lat, $6),
                           cluster_lon=COALESCE(cluster_lon, $7),
                           cluster_start_ts=$8,
                           segment_start_ts=$8,
                           recent_points=$9
                     WHERE user_id=$1
                    """,
                    user_id,
                    smoothed_lat,
                    smoothed_lon,
                    t,
                    total_m,
                    cluster_lat,
                    cluster_lon,
                    seg_start_ts,
                    recent_points_json,
                )
                await c.execute(
                    "UPDATE users SET reason_if_not_counted=$2, updated_at=now() WHERE user_id=$1",
                    user_id,
                    f"segment_accumulate:{int(total_m)}m",
                )
                return {"counted": 0, "reason": "segment_accumulate"}

            dt_sec = max(1.0, (t - seg_start_ts).total_seconds())
            speed_kmh = (total_m / 1000.0) / (dt_sec / 3600.0)
            if speed_kmh < SPEED_MIN_KMH or speed_kmh > SPEED_MAX_KMH:
                await c.execute(
                    """
                    UPDATE user_state
                       SET cluster_lat=$2,
                           cluster_lon=$3,
                           last_lat=$2,
                           last_lon=$3,
                           last_ts=$4,
                           residual_m=0,
                           cluster_start_ts=$4,
                           segment_start_ts=$4,
                           recent_points=$5
                     WHERE user_id=$1
                    """,
                    user_id,
                    reset_lat,
                    reset_lon,
                    t,
                    single_point_json,
                )
                await c.execute(
                    "UPDATE users SET reason_if_not_counted=$2, updated_at=now() WHERE user_id=$1",
                    user_id,
                    f"speed:{speed_kmh:.2f}",
                )
                return {"counted": 0, "reason": "speed", "speed": speed_kmh}

            steps = int(total_m / STEP_LENGTH_METERS)

            # Энергия (доступные шаги сегодня)
            u = await c.fetchrow("SELECT today_steps, total_steps, energy_max, energy_left, referrer_id FROM users WHERE user_id=$1", user_id)
            energy_left = int(u["energy_left"] if u and u["energy_left"] is not None else DAILY_ENERGY_STEPS)
            energy_max  = int(u["energy_max"]  if u and u["energy_max"]  is not None else DAILY_ENERGY_STEPS)
            today_steps = int(u["today_steps"] if u else 0)
            referrer_id = u["referrer_id"] if u else None

            # Сколько реально засчитать
            can_credit = max(0, min(steps, energy_max - today_steps))
            if can_credit <= 0:
                await c.execute(
                    """
                    UPDATE user_state
                       SET cluster_lat=$2,
                           cluster_lon=$3,
                           last_lat=$2,
                           last_lon=$3,
                           last_ts=$4,
                           residual_m=0,
                           cluster_start_ts=$4,
                           segment_start_ts=$4,
                           recent_points=$5
                     WHERE user_id=$1
                    """,
                    user_id,
                    reset_lat,
                    reset_lon,
                    t,
                    single_point_json,
                )
                await c.execute(
                    "UPDATE users SET reason_if_not_counted=$2, updated_at=now() WHERE user_id=$1",
                    user_id,
                    "no_energy",
                )
                return {"counted": 0, "reason": "no_energy"}

            # Начисления пользователю
            add_lbc = round(can_credit * LBC_PER_STEP, 8)
            await c.execute("""
                UPDATE users
                   SET today_steps = today_steps + $2,
                       total_steps = total_steps + $2,
                       today_lbc   = today_lbc   + $3,
                       total_lbc   = total_lbc   + $3,
                       energy_left = GREATEST(0, energy_left - $2),
                       reason_if_not_counted = NULL,
                       updated_at = now()
                 WHERE user_id=$1
            """, user_id, can_credit, add_lbc)

            # Реферальная капля
            if referrer_id and referrer_id != user_id:
                ref_add = round(can_credit * REF_LBC_PER_STEP, 8)
                await c.execute("""
                    UPDATE users
                       SET total_lbc = total_lbc + $2,
                            updated_at = now()
                     WHERE user_id=$1
                """, referrer_id, ref_add)

            residual_after = max(0.0, total_m - steps * STEP_LENGTH_METERS)

            prev_segment_start_ts = seg_start_ts
            prev_cluster_start_ts = st["cluster_start_ts"] or prev_segment_start_ts

            if residual_after > 0:
                # Остаток метров переносим в тот же временной интервал, чтобы античит видел цельное окно.
                new_cluster_start_ts = prev_cluster_start_ts or t
                new_segment_start_ts = prev_segment_start_ts or t
            else:
                new_cluster_start_ts = t
                new_segment_start_ts = t

            await c.execute(
                """
                UPDATE user_state
                   SET cluster_lat=$2,
                       cluster_lon=$3,
                       last_lat=$4,
                       last_lon=$5,
                       last_ts=$6,
                       residual_m=$7,
                       cluster_start_ts=$8,
                       segment_start_ts=$9,
                       recent_points=$10
                 WHERE user_id=$1
                """,
                user_id,
                smoothed_lat,
                smoothed_lon,
                smoothed_lat,
                smoothed_lon,
                t,
                residual_after,
                new_cluster_start_ts,
                new_segment_start_ts,
                recent_points_json,
            )

            return {"counted": can_credit, "speed": speed_kmh, "dist_m": total_m, "steps": steps}
