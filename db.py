
# db.py — LifeBlood DB API bridge (PATCH-110)
import os
import math
import asyncpg
from datetime import datetime, timezone, timedelta

DB_DSN = os.getenv("DB_DSN") or os.getenv("DATABASE_URL") or "postgresql://localhost:5432/lifeblood"

# Константы расчёта (FREE режим / MetaCross)
STEP_M = 0.75                      # средняя длина шага, м
CLUSTER_M = 100.0                  # размер пятна (кластер), м
SPEED_MIN_KMH = 3.0                # доп. скорость, км/ч
SPEED_MAX_KMH = 8.0
LBC_PER_STEP = 0.00042             # начисление за шаг пользователю (MetaCross spec 0.00042 LBC)
REF_LBC_PER_STEP = 0.0001          # реф. начисление за шаг
SIGNUP_BONUS = 25.0                # реф. бонус при регистрации, каждому
DAILY_ENERGY_STEPS = 3000          # суточная энергия MetaCross

def _tz3_start_of_today_utc(now_utc: datetime | None = None):
    now_utc = now_utc or datetime.now(timezone.utc)
    tz3 = timezone(timedelta(hours=3))
    today_tz3 = now_utc.astimezone(tz3).date()
    start_tz3 = datetime.combine(today_tz3, datetime.min.time(), tz3)
    return start_tz3.astimezone(timezone.utc)


def _haversine_m(lat1, lon1, lat2, lon2):
    # быстро и без внешних либ
    R = 6371000.0
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
            await c.execute("""
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
              ("energy_max",         "ALTER TABLE users ADD COLUMN IF NOT EXISTS energy_max INTEGER NOT NULL DEFAULT 3000"),
              ("energy_left",        "ALTER TABLE users ADD COLUMN IF NOT EXISTS energy_left INTEGER NOT NULL DEFAULT 3000"),
              ("dashboard_chat_id",  "ALTER TABLE users ADD COLUMN IF NOT EXISTS dashboard_chat_id BIGINT"),
              ("dashboard_msg_id",   "ALTER TABLE users ADD COLUMN IF NOT EXISTS dashboard_msg_id BIGINT"),
              ("reason_if_not_counted","ALTER TABLE users ADD COLUMN IF NOT EXISTS reason_if_not_counted TEXT"),
              ("updated_at",         "ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now()"),
              ("created_at",         "ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now()"),
            ]:
                await c.execute(ddl + ";")

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
              last_ts     TIMESTAMPTZ,
              cluster_start_ts TIMESTAMPTZ
            );
            """)
            await c.execute("ALTER TABLE user_state ADD COLUMN IF NOT EXISTS cluster_start_ts TIMESTAMPTZ;")

    # === служебные ===
    async def _ensure_user(self, user_id: int, username: str | None):
        await self.connect()
        async with self.pool.acquire() as c:
            row = await c.fetchrow("SELECT user_id FROM users WHERE user_id=$1", user_id)
            if row:
                await c.execute("UPDATE users SET username=$2, updated_at=now() WHERE user_id=$1", user_id, username)
                return False
            await c.execute("""
                INSERT INTO users (user_id, username, energy_max, energy_left)
                VALUES ($1, $2, $3, $3)
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
                await c.execute("UPDATE users SET total_lbc = COALESCE(total_lbc,0) + $2 WHERE user_id=$1", user_id, SIGNUP_BONUS)
                if ref:
                    await c.execute("UPDATE users SET total_lbc = COALESCE(total_lbc,0) + $2 WHERE user_id=$1", ref, SIGNUP_BONUS)
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
                   SET today_steps=0, today_lbc=0, energy_left=energy_max, updated_at=now()
                 WHERE user_id=$1 AND updated_at < $2
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
        """Принимает live-location. Считает шаги пачками по 100 м через центры «пятен»."""
        await self._ensure_user(user_id, username)
        await self._maybe_daily_reset(user_id)
        await self.connect()

        # ts -> datetime
        t = datetime.fromtimestamp(float(ts), tz=timezone.utc) if ts is not None else datetime.now(tz=timezone.utc)

        async with self.pool.acquire() as c, c.transaction():
            # Сохраним точку
            await c.execute("""
                INSERT INTO locations (user_id, ts, lat, lon, accuracy, heading)
                VALUES ($1,$2,$3,$4,$5,$6)
            """, user_id, t, lat, lon, accuracy, heading)

            # Текущее состояние кластера
            st = await c.fetchrow("SELECT cluster_lat, cluster_lon, last_ts, cluster_start_ts FROM user_state WHERE user_id=$1", user_id)
            if not st or st["cluster_lat"] is None or st["cluster_lon"] is None:
                # Инициализация пятна
                await c.execute("""
                    INSERT INTO user_state (user_id, cluster_lat, cluster_lon, last_ts, cluster_start_ts)
                    VALUES ($1,$2,$3,$4,$4)
                    ON CONFLICT (user_id) DO UPDATE
                    SET cluster_lat=EXCLUDED.cluster_lat,
                        cluster_lon=EXCLUDED.cluster_lon,
                        last_ts=EXCLUDED.last_ts,
                        cluster_start_ts=EXCLUDED.cluster_start_ts
                """, user_id, lat, lon, t)
                await c.execute("UPDATE users SET reason_if_not_counted=$2, updated_at=now() WHERE user_id=$1",
                                user_id, "cluster_init")
                return {"counted": 0, "reason": "cluster_init"}

            cl_lat, cl_lon = st["cluster_lat"], st["cluster_lon"]
            last_ts = st["last_ts"] or t
            cluster_start_ts = st["cluster_start_ts"] or last_ts
            dist_m = _haversine_m(cl_lat, cl_lon, lat, lon)

            # Пока не «набежало» 100 м — просто обновляем last_ts (время последней точки) и причину
            if dist_m < CLUSTER_M:
                await c.execute("""
                    UPDATE user_state
                       SET last_ts=$2,
                           cluster_start_ts=COALESCE(cluster_start_ts, $2)
                     WHERE user_id=$1
                """, user_id, t)
                await c.execute("UPDATE users SET reason_if_not_counted=$2, updated_at=now() WHERE user_id=$1",
                                user_id, f"cluster_accumulate:{int(dist_m)}m")
                return {"counted": 0, "reason": "cluster_accumulate"}

            # Проверка скорости
            dt_sec = max(1.0, (t - cluster_start_ts).total_seconds())
            speed_kmh = (dist_m/1000.0)/(dt_sec/3600.0)
            if speed_kmh < SPEED_MIN_KMH or speed_kmh > SPEED_MAX_KMH:
                # Сдвигаем центр пятна, но не считаем
                await c.execute("""
                    UPDATE user_state SET cluster_lat=$2, cluster_lon=$3, last_ts=$4, cluster_start_ts=$4 WHERE user_id=$1
                """, user_id, lat, lon, t)
                await c.execute("UPDATE users SET reason_if_not_counted=$2, updated_at=now() WHERE user_id=$1",
                                user_id, f"speed:{speed_kmh:.2f}kmh_out_of_range")
                return {"counted": 0, "reason": "speed_out_of_range", "speed": speed_kmh}

            # Сколько шагов из дистанции
            steps = int(dist_m / STEP_M)
            if steps <= 0:
                await c.execute("UPDATE users SET reason_if_not_counted=$2, updated_at=now() WHERE user_id=$1",
                                user_id, "distance<step")
                # Сдвигаем пятно, чтобы не клинить
                await c.execute("UPDATE user_state SET cluster_lat=$2, cluster_lon=$3, last_ts=$4, cluster_start_ts=$4 WHERE user_id=$1",
                                user_id, lat, lon, t)
                return {"counted": 0, "reason": "too_small"}

            # Энергия (доступные шаги сегодня)
            u = await c.fetchrow("SELECT today_steps, total_steps, energy_max, energy_left, referrer_id FROM users WHERE user_id=$1", user_id)
            energy_left = int(u["energy_left"] if u and u["energy_left"] is not None else DAILY_ENERGY_STEPS)
            energy_max  = int(u["energy_max"]  if u and u["energy_max"]  is not None else DAILY_ENERGY_STEPS)
            today_steps = int(u["today_steps"] if u else 0)
            referrer_id = u["referrer_id"] if u else None

            # Сколько реально засчитать
            can_credit = max(0, min(steps, energy_max - today_steps))
            if can_credit <= 0:
                await c.execute("UPDATE users SET reason_if_not_counted=$2, updated_at=now() WHERE user_id=$1",
                                user_id, "no_energy")
                # всё равно передвинем пятно
                await c.execute("UPDATE user_state SET cluster_lat=$2, cluster_lon=$3, last_ts=$4, cluster_start_ts=$4 WHERE user_id=$1",
                                user_id, lat, lon, t)
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

            # Передвигаем центр пятна
            await c.execute("""
                UPDATE user_state SET cluster_lat=$2, cluster_lon=$3, last_ts=$4, cluster_start_ts=$4 WHERE user_id=$1
            """, user_id, lat, lon, t)

            return {"counted": can_credit, "speed": speed_kmh, "dist_m": dist_m}

