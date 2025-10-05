#!/usr/bin/env python3
from pathlib import Path
from textwrap import dedent

ROOT = Path(__file__).resolve().parent
if not (ROOT / "step_config.py").exists():
    ROOT = ROOT.parent

STEP_CONFIG_PATH = ROOT / "step_config.py"
DB_PATH = ROOT / "db.py"

STEP_CONFIG_BODY = dedent(
    '''\
    """Step/energy accrual constants for the LifeBlood MetaCross flow."""

    from typing import Final

    # Base geometry
    STEP_LENGTH_METERS: Final[float] = 0.75  # см. Documentation/EN_WP_1_extracted.txt строки 70-79 (длина шага 0.75 м)
    CLUSTER_DISTANCE_METERS: Final[float] = 15.0  # см. Documentation/EN_WP_1_extracted.txt строки 528-539 + техплан PATCH-110
    EARTH_RADIUS_METERS: Final[float] = 6_371_000.0  # WGS84 усреднённый радиус Земли для хаверсина

    # Off-chain MetaCross (базовый) конфиг
    ENERGY_STEPS_PER_UNIT: Final[int] = 3_000  # см. Documentation/EN_WP_1_extracted.txt строки 511-513 (1 энергия = 3000 шагов)
    BASE_METACROSS_ENERGY_UNITS: Final[float] = 3.0  # базово 3 энергии (редактируйте при необходимости)
    BASE_METACROSS_SPEED_MIN_KMH: Final[float] = 3.0  # см. Documentation/EN_WP_1_extracted.txt строки 478-479 (Casual sneakers 3-8 км/ч)
    BASE_METACROSS_SPEED_MAX_KMH: Final[float] = 8.0  # см. Documentation/EN_WP_1_extracted.txt строки 478-479 (Casual sneakers 3-8 км/ч)
    NFT_BASE_LBC_PER_STEP: Final[float] = 0.0042  # см. Documentation/EN_WP_1_extracted.txt строки 538-543 (базовое NFT начисление)
    BASE_METACROSS_LBC_MULTIPLIER: Final[float] = 0.1  # см. Documentation/EN_WP_1_extracted.txt строка 531 (MetaCross = 10% NFT дохода)
    BASE_METACROSS_LBC_PER_STEP: Final[float] = NFT_BASE_LBC_PER_STEP * BASE_METACROSS_LBC_MULTIPLIER

    # Activity filters
    SPEED_MIN_KMH: Final[float] = BASE_METACROSS_SPEED_MIN_KMH
    SPEED_MAX_KMH: Final[float] = BASE_METACROSS_SPEED_MAX_KMH
    GPS_MAX_ACCURACY_METERS: Final[float] = 100.0  # см. Documentation/EN_WP_1_extracted.txt строки 72-85 + PATCH-110 (лимит точности 25 м для устойчивого GPS)

    # GPS smoothing / anti-cheat
    SMOOTHING_WINDOW_POINTS: Final[int] = 3  # PATCH-110 античит: окно из 3 последних точек
    MAX_JUMP_METERS: Final[float] = 120.0  # PATCH-110 античит: отсечение скачка >120 м
    MIN_JUMP_INTERVAL_SEC: Final[int] = 5  # PATCH-110 античит: проверка скачка в окне <10 сек

    # Accruals
    LBC_PER_STEP: Final[float] = BASE_METACROSS_LBC_PER_STEP
    REF_LBC_PER_STEP: Final[float] = 0.00010  # см. Documentation/EN_WP_1_extracted.txt раздел Free entry + PATCH-110
    SIGNUP_BONUS_LBC: Final[float] = 25.0  # см. Documentation/EN_WP_1_extracted.txt раздел Free entry + PATCH-110

    # Производное суточное ограничение в шагах
    DAILY_ENERGY_STEPS: Final[int] = int(BASE_METACROSS_ENERGY_UNITS * ENERGY_STEPS_PER_UNIT)

    __all__ = [
        "STEP_LENGTH_METERS",
        "CLUSTER_DISTANCE_METERS",
        "EARTH_RADIUS_METERS",
        "ENERGY_STEPS_PER_UNIT",
        "BASE_METACROSS_ENERGY_UNITS",
        "BASE_METACROSS_SPEED_MIN_KMH",
        "BASE_METACROSS_SPEED_MAX_KMH",
        "SPEED_MIN_KMH",
        "SPEED_MAX_KMH",
        "GPS_MAX_ACCURACY_METERS",
        "SMOOTHING_WINDOW_POINTS",
        "MAX_JUMP_METERS",
        "MIN_JUMP_INTERVAL_SEC",
        "NFT_BASE_LBC_PER_STEP",
        "BASE_METACROSS_LBC_MULTIPLIER",
        "BASE_METACROSS_LBC_PER_STEP",
        "LBC_PER_STEP",
        "REF_LBC_PER_STEP",
        "SIGNUP_BONUS_LBC",
        "DAILY_ENERGY_STEPS",
    ]
    '''
) + "\n"

OLD_STEP_IMPORT_BLOCK = dedent(
    '''\
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
    '''
) + "\n"

NEW_STEP_IMPORT_BLOCK = dedent(
    '''\
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
        ENERGY_STEPS_PER_UNIT,
        BASE_METACROSS_ENERGY_UNITS,
        BASE_METACROSS_LBC_PER_STEP,
        BASE_METACROSS_SPEED_MIN_KMH,
        BASE_METACROSS_SPEED_MAX_KMH,
    )
    '''
) + "\n"

FORMAT_DECIMAL_SNIPPET = (
    "def _format_decimal(value: float, digits: int) -> str:\n"
    "    quant = Decimal(\"1\").scaleb(-digits)\n"
    "    return format(Decimal(str(value)).quantize(quant, rounding=ROUND_HALF_UP), \"f\")\n\n\n"
)

OLD_HAVERSINE = dedent(
    '''\
    def _haversine_m(lat1, lon1, lat2, lon2):
        # быстро и без внешних либ
        R = EARTH_RADIUS_METERS
        p = math.pi/180.0
        dlat = (lat2-lat1)*p
        dlon = (lon2-lon1)*p
        a = (math.sin(dlat/2)**2 +
             math.cos(lat1*p)*math.cos(lat2*p)*math.sin(dlon/2)**2)
        return 2*R*math.asin(math.sqrt(a))
    '''
) + "\n\n"

NEW_HAVERSINE = dedent(
    '''\
    def _haversine_m(lat1, lon1, lat2, lon2):
        # быстро и без внешних либ
        R = EARTH_RADIUS_METERS
        p = math.pi / 180.0
        dlat = (lat2 - lat1) * p
        dlon = (lon2 - lon1) * p
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin(dlon / 2) ** 2
        )
        return 2 * R * math.asin(math.sqrt(a))
    '''
) + "\n\n"

ENSURE_SCHEMA_LINES = [
    "    async def ensure_schema(self):",
    "        await self.connect()",
    "        async with self.pool.acquire() as c:",
    "            base_energy_units = _format_decimal(BASE_METACROSS_ENERGY_UNITS, 2)",
    "            base_lbc_per_step = _format_decimal(BASE_METACROSS_LBC_PER_STEP, 8)",
    "            base_speed_min = _format_decimal(BASE_METACROSS_SPEED_MIN_KMH, 2)",
    "            base_speed_max = _format_decimal(BASE_METACROSS_SPEED_MAX_KMH, 2)",
    "            steps_per_unit = int(ENERGY_STEPS_PER_UNIT)",
    "            await c.execute(",
    "                f\"\"\"",
    "                CREATE TABLE IF NOT EXISTS users (",
    "                  user_id            BIGINT PRIMARY KEY,",
    "                  username           TEXT,",
    "                  referrer_id        BIGINT,",
    "                  today_steps        INTEGER NOT NULL DEFAULT 0,",
    "                  total_steps        BIGINT  NOT NULL DEFAULT 0,",
    "                  today_lbc          NUMERIC(20,8) NOT NULL DEFAULT 0,",
    "                  total_lbc          NUMERIC(20,8) NOT NULL DEFAULT 0,",
    "                  energy_max         INTEGER NOT NULL DEFAULT {DAILY_ENERGY_STEPS},",
    "                  energy_left        INTEGER NOT NULL DEFAULT {DAILY_ENERGY_STEPS},",
    "                  energy_reset_at    TIMESTAMPTZ,",
    "                  active_nft_template_id INTEGER,",
    "                  energy_units       NUMERIC(10,2) NOT NULL DEFAULT {base_energy_units},",
    "                  steps_per_unit     INTEGER NOT NULL DEFAULT {steps_per_unit},",
    "                  lbc_per_step       NUMERIC(20,8) NOT NULL DEFAULT {base_lbc_per_step},",
    "                  speed_min_kmh      NUMERIC(6,2) NOT NULL DEFAULT {base_speed_min},",
    "                  speed_max_kmh      NUMERIC(6,2) NOT NULL DEFAULT {base_speed_max},",
    "                  dashboard_chat_id  BIGINT,",
    "                  dashboard_msg_id   BIGINT,",
    "                  reason_if_not_counted TEXT,",
    "                  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),",
    "                  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()",
    "                );",
    "                \"\"\"",
    "            )",
    "            for col, ddl in [",
    "                (\"referrer_id\", \"ALTER TABLE users ADD COLUMN IF NOT EXISTS referrer_id BIGINT\"),",
    "                (\"today_steps\", \"ALTER TABLE users ADD COLUMN IF NOT EXISTS today_steps INTEGER NOT NULL DEFAULT 0\"),",
    "                (\"total_steps\", \"ALTER TABLE users ADD COLUMN IF NOT EXISTS total_steps BIGINT NOT NULL DEFAULT 0\"),",
    "                (\"today_lbc\", \"ALTER TABLE users ADD COLUMN IF NOT EXISTS today_lbc NUMERIC(20,8) NOT NULL DEFAULT 0\"),",
    "                (\"total_lbc\", \"ALTER TABLE users ADD COLUMN IF NOT EXISTS total_lbc NUMERIC(20,8) NOT NULL DEFAULT 0\"),",
    "                (\"energy_max\", f\"ALTER TABLE users ADD COLUMN IF NOT EXISTS energy_max INTEGER NOT NULL DEFAULT {DAILY_ENERGY_STEPS}\"),",
    "                (\"energy_left\", f\"ALTER TABLE users ADD COLUMN IF NOT EXISTS energy_left INTEGER NOT NULL DEFAULT {DAILY_ENERGY_STEPS}\"),",
    "                (\"energy_reset_at\", \"ALTER TABLE users ADD COLUMN IF NOT EXISTS energy_reset_at TIMESTAMPTZ\"),",
    "                (\"active_nft_template_id\", \"ALTER TABLE users ADD COLUMN IF NOT EXISTS active_nft_template_id INTEGER\"),",
    "                (\"energy_units\", f\"ALTER TABLE users ADD COLUMN IF NOT EXISTS energy_units NUMERIC(10,2) NOT NULL DEFAULT {base_energy_units}\"),",
    "                (\"steps_per_unit\", f\"ALTER TABLE users ADD COLUMN IF NOT EXISTS steps_per_unit INTEGER NOT NULL DEFAULT {steps_per_unit}\"),",
    "                (\"lbc_per_step\", f\"ALTER TABLE users ADD COLUMN IF NOT EXISTS lbc_per_step NUMERIC(20,8) NOT NULL DEFAULT {base_lbc_per_step}\"),",
    "                (\"speed_min_kmh\", f\"ALTER TABLE users ADD COLUMN IF NOT EXISTS speed_min_kmh NUMERIC(6,2) NOT NULL DEFAULT {base_speed_min}\"),",
    "                (\"speed_max_kmh\", f\"ALTER TABLE users ADD COLUMN IF NOT EXISTS speed_max_kmh NUMERIC(6,2) NOT NULL DEFAULT {base_speed_max}\"),",
    "                (\"dashboard_chat_id\", \"ALTER TABLE users ADD COLUMN IF NOT EXISTS dashboard_chat_id BIGINT\"),",
    "                (\"dashboard_msg_id\", \"ALTER TABLE users ADD COLUMN IF NOT EXISTS dashboard_msg_id BIGINT\"),",
    "                (\"reason_if_not_counted\", \"ALTER TABLE users ADD COLUMN IF NOT EXISTS reason_if_not_counted TEXT\"),",
    "                (\"updated_at\", \"ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now()\"),",
    "                (\"created_at\", \"ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now()\"),",
    "            ]:",
    "                await c.execute(ddl + \";\")",
    "            for ddl in [",
    "                f\"ALTER TABLE users ALTER COLUMN energy_max SET DEFAULT {DAILY_ENERGY_STEPS}\",",
    "                f\"ALTER TABLE users ALTER COLUMN energy_left SET DEFAULT {DAILY_ENERGY_STEPS}\",",
    "                f\"ALTER TABLE users ALTER COLUMN energy_units SET DEFAULT {base_energy_units}\",",
    "                f\"ALTER TABLE users ALTER COLUMN steps_per_unit SET DEFAULT {steps_per_unit}\",",
    "                f\"ALTER TABLE users ALTER COLUMN lbc_per_step SET DEFAULT {base_lbc_per_step}\",",
    "                f\"ALTER TABLE users ALTER COLUMN speed_min_kmh SET DEFAULT {base_speed_min}\",",
    "                f\"ALTER TABLE users ALTER COLUMN speed_max_kmh SET DEFAULT {base_speed_max}\",",
    "            ]:",
    "                await c.execute(ddl + \";\")",
    "            await c.execute(",
    "                \"\"\"",
    "                UPDATE users",
    "                   SET energy_reset_at = COALESCE(energy_reset_at, updated_at, created_at, now())",
    "                 WHERE energy_reset_at IS NULL",
    "                \"\"\"",
    "            )",
    "            await c.execute(",
    "                \"\"\"",
    "                CREATE TABLE IF NOT EXISTS nft_templates (",
    "                  id SERIAL PRIMARY KEY,",
    "                  slug TEXT UNIQUE NOT NULL,",
    "                  title TEXT NOT NULL,",
    "                  kind TEXT NOT NULL,",
    "                  is_onchain BOOLEAN NOT NULL DEFAULT FALSE,",
    "                  ton_collection TEXT,",
    "                  energy_units NUMERIC(10,2) NOT NULL,",
    "                  steps_per_unit INTEGER NOT NULL,",
    "                  lbc_per_step NUMERIC(20,8) NOT NULL,",
    "                  speed_min_kmh NUMERIC(6,2) NOT NULL,",
    "                  speed_max_kmh NUMERIC(6,2) NOT NULL,",
    "                  metadata JSONB,",
    "                  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),",
    "                  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()",
    "                );",
    "                \"\"\"",
    "            )",
    "            await c.execute(\"CREATE INDEX IF NOT EXISTS idx_nft_templates_kind ON nft_templates(kind);\")",
    "            await c.execute(",
    "                \"\"\"",
    "                CREATE TABLE IF NOT EXISTS user_nfts (",
    "                  id BIGSERIAL PRIMARY KEY,",
    "                  user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,",
    "                  template_id INTEGER NOT NULL REFERENCES nft_templates(id),",
    "                  ton_wallet TEXT,",
    "                  token_address TEXT,",
    "                  token_id TEXT,",
    "                  metadata JSONB,",
    "                  is_active BOOLEAN NOT NULL DEFAULT FALSE,",
    "                  activated_at TIMESTAMPTZ,",
    "                  deactivated_at TIMESTAMPTZ,",
    "                  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),",
    "                  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()",
    "                );",
    "                \"\"\"",
    "            )",
    "            await c.execute(\"CREATE INDEX IF NOT EXISTS idx_user_nfts_user ON user_nfts(user_id);\")",
    "            await c.execute(\"CREATE INDEX IF NOT EXISTS idx_user_nfts_template ON user_nfts(template_id);\")",
    "            await c.execute(",
    "                \"CREATE UNIQUE INDEX IF NOT EXISTS idx_user_nfts_user_active ON user_nfts(user_id) WHERE is_active;\"",
    "            )",
    "            await c.execute(",
    "                \"CREATE UNIQUE INDEX IF NOT EXISTS idx_user_nfts_token ON user_nfts(user_id, template_id, token_id);\"",
    "            )",
    "            await c.execute(",
    "                \"\"\"",
    "                DO $$",
    "                BEGIN",
    "                    IF NOT EXISTS (",
    "                        SELECT 1",
    "                          FROM pg_constraint",
    "                         WHERE conname = 'users_active_nft_template_id_fkey'",
    "                    ) THEN",
    "                        ALTER TABLE users",
    "                            ADD CONSTRAINT users_active_nft_template_id_fkey",
    "                            FOREIGN KEY (active_nft_template_id)",
    "                            REFERENCES nft_templates(id);",
    "                    END IF;",
    "                END $$;",
    "                \"\"\"",
    "            )",
    "            # точки гео",
    "            await c.execute(",
    "                \"\"\"",
    "                CREATE TABLE IF NOT EXISTS locations (",
    "                  id        BIGSERIAL PRIMARY KEY,",
    "                  user_id   BIGINT NOT NULL,",
    "                  ts        TIMESTAMPTZ NOT NULL,",
    "                  lat       DOUBLE PRECISION NOT NULL,",
    "                  lon       DOUBLE PRECISION NOT NULL,",
    "                  accuracy  DOUBLE PRECISION,",
    "                  heading   INTEGER,",
    "                  created_at TIMESTAMPTZ NOT NULL DEFAULT now()",
    "                );",
    "                CREATE INDEX IF NOT EXISTS idx_locations_user_ts ON locations(user_id, ts DESC);",
    "                \"\"\"",
    "            )",
    "            # состояние «пятна» (кластер)",
    "            await c.execute(",
    "                \"\"\"",
    "                CREATE TABLE IF NOT EXISTS user_state (",
    "                  user_id     BIGINT PRIMARY KEY,",
    "                  cluster_lat DOUBLE PRECISION,",
    "                  cluster_lon DOUBLE PRECISION,",
    "                  last_lat    DOUBLE PRECISION,",
    "                  last_lon    DOUBLE PRECISION,",
    "                  last_ts     TIMESTAMPTZ,",
    "                  residual_m  DOUBLE PRECISION,",
    "                  cluster_start_ts TIMESTAMPTZ,",
    "                  segment_start_ts TIMESTAMPTZ,",
    "                  recent_points JSONB",
    "                );",
    "                \"\"\"",
    "            )",
    "            for ddl in [",
    "                \"ALTER TABLE user_state ADD COLUMN IF NOT EXISTS cluster_start_ts TIMESTAMPTZ\",",
    "                \"ALTER TABLE user_state ADD COLUMN IF NOT EXISTS last_lat DOUBLE PRECISION\",",
    "                \"ALTER TABLE user_state ADD COLUMN IF NOT EXISTS last_lon DOUBLE PRECISION\",",
    "                \"ALTER TABLE user_state ADD COLUMN IF NOT EXISTS residual_m DOUBLE PRECISION\",",
    "                \"ALTER TABLE user_state ADD COLUMN IF NOT EXISTS segment_start_ts TIMESTAMPTZ\",",
    "                \"ALTER TABLE user_state ADD COLUMN IF NOT EXISTS recent_points JSONB\",",
    "            ]:",
    "                await c.execute(ddl + \";\")",
]

NEW_ENSURE_SCHEMA = "\n".join(ENSURE_SCHEMA_LINES)

def expect_replace(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"Не нашёл фрагмент: {label}")
    return text.replace(old, new, 1)

def rewrite_step_config() -> None:
    if not STEP_CONFIG_PATH.exists():
        raise RuntimeError("step_config.py не найден — запусти скрипт из корня проекта.")
    STEP_CONFIG_PATH.write_text(STEP_CONFIG_BODY, encoding="utf-8")
    print("✔ step_config.py переписан (MetaCross-константы обновлены).")

def patch_db() -> None:
    if not DB_PATH.exists():
        raise RuntimeError("db.py не найден — запусти скрипт из корня проекта.")
    text = DB_PATH.read_text(encoding="utf-8")

    if "from decimal import Decimal, ROUND_HALF_UP" not in text:
        target = "import json\nimport asyncpg\n"
        replacement = "import json\nfrom decimal import Decimal, ROUND_HALF_UP\nimport asyncpg\n"
        if target not in text:
            raise RuntimeError("Не удалось вставить импорт Decimal (нет ожидаемого блока).")
        text = text.replace(target, replacement, 1)

    text = expect_replace(text, OLD_STEP_IMPORT_BLOCK, NEW_STEP_IMPORT_BLOCK, "импорт step_config")
    if "def _format_decimal(" not in text:
        anchor = (
            'DB_DSN = os.getenv("DB_DSN") or os.getenv("DATABASE_URL") or "postgresql://localhost:5432/lifeblood"\n\n\n'
        )
        if anchor not in text:
            raise RuntimeError("Не нашёл место для _format_decimal.")
        text = text.replace(anchor, anchor + FORMAT_DECIMAL_SNIPPET, 1)

    text = expect_replace(text, OLD_HAVERSINE, NEW_HAVERSINE, "_haversine_m")

    marker = "    async def ensure_schema(self):"
    end_marker = "    # === служебные ==="
    if marker not in text or end_marker not in text:
        raise RuntimeError("Не нашёл границы ensure_schema.")
    start = text.index(marker)
    end = text.index(end_marker, start)
    ensure_schema_block = NEW_ENSURE_SCHEMA.rstrip() + "\n"
    text = text[:start] + ensure_schema_block + "\n" + text[end:]

    if not text.endswith("\n"):
        text += "\n"
    DB_PATH.write_text(text, encoding="utf-8")
    print("✔ db.py обновлён (NFT-схема и дефолты энергии добавлены).")

def main() -> None:
    rewrite_step_config()
    patch_db()
    print("Готово: можно перезапускать ensure_schema и мигрировать данные.")

if __name__ == "__main__":
    main()
