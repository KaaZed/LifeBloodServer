#!/usr/bin/env python3

import shutil
from pathlib import Path
import textwrap


CONST_BLOCK = textwrap.dedent('''\
BASE_OFFCHAIN_NFT_SLUG = "metacross_base_offchain"
BASE_OFFCHAIN_NFT_TITLE = "MetaCross базовый офчейн"
BASE_OFFCHAIN_NFT_KIND = "offchain"
BASE_OFFCHAIN_NFT_METADATA = {
    "note": "Базовый офчейн MetaCross NFT; параметры редактируются централизованно в step_config.py.",
    "source": "Documentation/EN_WP_1_extracted.txt строки 478-543",
}
''').strip() + "\n\n"

ENSURE_SCHEMA_BODY = '''\
async def ensure_schema(self):
    await self.connect()
    async with self.pool.acquire() as c:
        base_energy_units = _format_decimal(BASE_METACROSS_ENERGY_UNITS, 2)
        base_lbc_per_step = _format_decimal(BASE_METACROSS_LBC_PER_STEP, 8)
        base_speed_min = _format_decimal(BASE_METACROSS_SPEED_MIN_KMH, 2)
        base_speed_max = _format_decimal(BASE_METACROSS_SPEED_MAX_KMH, 2)
        steps_per_unit = int(ENERGY_STEPS_PER_UNIT)
        base_energy_units_dec = Decimal(base_energy_units)
        base_lbc_per_step_dec = Decimal(base_lbc_per_step)
        base_speed_min_dec = Decimal(base_speed_min)
        base_speed_max_dec = Decimal(base_speed_max)
        base_energy_limit_steps = int(base_energy_units_dec * steps_per_unit)
        base_template_metadata_json = json.dumps(
            BASE_OFFCHAIN_NFT_METADATA,
            ensure_ascii=False,
        )
        async with c.transaction():
            await c.execute(
                f"""
                CREATE TABLE IF NOT EXISTS users (
                  user_id            BIGINT PRIMARY KEY,
                  username           TEXT,
                  referrer_id        BIGINT,
                  today_steps        INTEGER NOT NULL DEFAULT 0,
                  total_steps        BIGINT  NOT NULL DEFAULT 0,
                  today_lbc          NUMERIC(20,8) NOT NULL DEFAULT 0,
                  total_lbc          NUMERIC(20,8) NOT NULL DEFAULT 0,
                  energy_max         INTEGER NOT NULL DEFAULT {DAILY_ENERGY_STEPS},
                  energy_left        INTEGER NOT NULL DEFAULT {DAILY_ENERGY_STEPS},
                  energy_reset_at    TIMESTAMPTZ,
                  active_nft_template_id INTEGER,
                  energy_units       NUMERIC(10,2) NOT NULL DEFAULT {base_energy_units},
                  steps_per_unit     INTEGER NOT NULL DEFAULT {steps_per_unit},
                  lbc_per_step       NUMERIC(20,8) NOT NULL DEFAULT {base_lbc_per_step},
                  speed_min_kmh      NUMERIC(6,2) NOT NULL DEFAULT {base_speed_min},
                  speed_max_kmh      NUMERIC(6,2) NOT NULL DEFAULT {base_speed_max},
                  dashboard_chat_id  BIGINT,
                  dashboard_msg_id   BIGINT,
                  reason_if_not_counted TEXT,
                  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
                  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
                );
                """
            )
            for _, ddl in [
                ("referrer_id", "ALTER TABLE users ADD COLUMN IF NOT EXISTS referrer_id BIGINT"),
                ("today_steps", "ALTER TABLE users ADD COLUMN IF NOT EXISTS today_steps INTEGER NOT NULL DEFAULT 0"),
                ("total_steps", "ALTER TABLE users ADD COLUMN IF NOT EXISTS total_steps BIGINT NOT NULL DEFAULT 0"),
                ("today_lbc", "ALTER TABLE users ADD COLUMN IF NOT EXISTS today_lbc NUMERIC(20,8) NOT NULL DEFAULT 0"),
                ("total_lbc", "ALTER TABLE users ADD COLUMN IF NOT EXISTS total_lbc NUMERIC(20,8) NOT NULL DEFAULT 0"),
                ("energy_max", f"ALTER TABLE users ADD COLUMN IF NOT EXISTS energy_max INTEGER NOT NULL DEFAULT {DAILY_ENERGY_STEPS}"),
                ("energy_left", f"ALTER TABLE users ADD COLUMN IF NOT EXISTS energy_left INTEGER NOT NULL DEFAULT {DAILY_ENERGY_STEPS}"),
                ("energy_reset_at", "ALTER TABLE users ADD COLUMN IF NOT EXISTS energy_reset_at TIMESTAMPTZ"),
                ("active_nft_template_id", "ALTER TABLE users ADD COLUMN IF NOT EXISTS active_nft_template_id INTEGER"),
                ("energy_units", f"ALTER TABLE users ADD COLUMN IF NOT EXISTS energy_units NUMERIC(10,2) NOT NULL DEFAULT {base_energy_units}"),
                ("steps_per_unit", f"ALTER TABLE users ADD COLUMN IF NOT EXISTS steps_per_unit INTEGER NOT NULL DEFAULT {steps_per_unit}"),
                ("lbc_per_step", f"ALTER TABLE users ADD COLUMN IF NOT EXISTS lbc_per_step NUMERIC(20,8) NOT NULL DEFAULT {base_lbc_per_step}"),
                ("speed_min_kmh", f"ALTER TABLE users ADD COLUMN IF NOT EXISTS speed_min_kmh NUMERIC(6,2) NOT NULL DEFAULT {base_speed_min}"),
                ("speed_max_kmh", f"ALTER TABLE users ADD COLUMN IF NOT EXISTS speed_max_kmh NUMERIC(6,2) NOT NULL DEFAULT {base_speed_max}"),
                ("dashboard_chat_id", "ALTER TABLE users ADD COLUMN IF NOT EXISTS dashboard_chat_id BIGINT"),
                ("dashboard_msg_id", "ALTER TABLE users ADD COLUMN IF NOT EXISTS dashboard_msg_id BIGINT"),
                ("reason_if_not_counted", "ALTER TABLE users ADD COLUMN IF NOT EXISTS reason_if_not_counted TEXT"),
                ("updated_at", "ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now()"),
                ("created_at", "ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now()"),
            ]:
                await c.execute(ddl + ";")
            for ddl in [
                f"ALTER TABLE users ALTER COLUMN energy_max SET DEFAULT {DAILY_ENERGY_STEPS}",
                f"ALTER TABLE users ALTER COLUMN energy_left SET DEFAULT {DAILY_ENERGY_STEPS}",
                f"ALTER TABLE users ALTER COLUMN energy_units SET DEFAULT {base_energy_units}",
                f"ALTER TABLE users ALTER COLUMN steps_per_unit SET DEFAULT {steps_per_unit}",
                f"ALTER TABLE users ALTER COLUMN lbc_per_step SET DEFAULT {base_lbc_per_step}",
                f"ALTER TABLE users ALTER COLUMN speed_min_kmh SET DEFAULT {base_speed_min}",
                f"ALTER TABLE users ALTER COLUMN speed_max_kmh SET DEFAULT {base_speed_max}",
            ]:
                await c.execute(ddl + ";")
            await c.execute(
                """
                UPDATE users
                   SET energy_reset_at = COALESCE(energy_reset_at, updated_at, created_at, now())
                 WHERE energy_reset_at IS NULL
                """
            )
            await c.execute(
                """
                CREATE TABLE IF NOT EXISTS nft_templates (
                  id SERIAL PRIMARY KEY,
                  slug TEXT UNIQUE NOT NULL,
                  title TEXT NOT NULL,
                  kind TEXT NOT NULL,
                  is_onchain BOOLEAN NOT NULL DEFAULT FALSE,
                  ton_collection TEXT,
                  energy_units NUMERIC(10,2) NOT NULL,
                  steps_per_unit INTEGER NOT NULL,
                  lbc_per_step NUMERIC(20,8) NOT NULL,
                  speed_min_kmh NUMERIC(6,2) NOT NULL,
                  speed_max_kmh NUMERIC(6,2) NOT NULL,
                  metadata JSONB,
                  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );
                """
            )
            await c.execute("CREATE INDEX IF NOT EXISTS idx_nft_templates_kind ON nft_templates(kind);")
            await c.execute(
                """
                CREATE TABLE IF NOT EXISTS user_nfts (
                  id BIGSERIAL PRIMARY KEY,
                  user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                  template_id INTEGER NOT NULL REFERENCES nft_templates(id),
                  ton_wallet TEXT,
                  token_address TEXT,
                  token_id TEXT,
                  metadata JSONB,
                  is_active BOOLEAN NOT NULL DEFAULT FALSE,
                  activated_at TIMESTAMPTZ,
                  deactivated_at TIMESTAMPTZ,
                  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );
                """
            )
            await c.execute("CREATE INDEX IF NOT EXISTS idx_user_nfts_user ON user_nfts(user_id);")
            await c.execute("CREATE INDEX IF NOT EXISTS idx_user_nfts_template ON user_nfts(template_id);")
            await c.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_user_nfts_user_active ON user_nfts(user_id) WHERE is_active;"
            )
            await c.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_user_nfts_token ON user_nfts(user_id, template_id, token_id);"
            )
            await c.execute(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1
                          FROM pg_constraint
                         WHERE conname = 'users_active_nft_template_id_fkey'
                    ) THEN
                        ALTER TABLE users
                            ADD CONSTRAINT users_active_nft_template_id_fkey
                            FOREIGN KEY (active_nft_template_id)
                            REFERENCES nft_templates(id);
                    END IF;
                END $$;
                """
            )
            for ddl in [
                "ALTER TABLE user_state ADD COLUMN IF NOT EXISTS cluster_start_ts TIMESTAMPTZ",
                "ALTER TABLE user_state ADD COLUMN IF NOT EXISTS last_lat DOUBLE PRECISION",
                "ALTER TABLE user_state ADD COLUMN IF NOT EXISTS last_lon DOUBLE PRECISION",
                "ALTER TABLE user_state ADD COLUMN IF NOT EXISTS residual_m DOUBLE PRECISION",
                "ALTER TABLE user_state ADD COLUMN IF NOT EXISTS segment_start_ts TIMESTAMPTZ",
                "ALTER TABLE user_state ADD COLUMN IF NOT EXISTS recent_points JSONB",
            ]:
                await c.execute(ddl + ";")

            base_template_row = await c.fetchrow(
                """
                INSERT INTO nft_templates (
                    slug,
                    title,
                    kind,
                    is_onchain,
                    ton_collection,
                    energy_units,
                    steps_per_unit,
                    lbc_per_step,
                    speed_min_kmh,
                    speed_max_kmh,
                    metadata
                )
                VALUES ($1, $2, $3, FALSE, NULL, $4, $5, $6, $7, $8, $9::jsonb)
                ON CONFLICT (slug) DO UPDATE
                SET title = EXCLUDED.title,
                    kind = EXCLUDED.kind,
                    is_onchain = EXCLUDED.is_onchain,
                    ton_collection = EXCLUDED.ton_collection,
                    energy_units = EXCLUDED.energy_units,
                    steps_per_unit = EXCLUDED.steps_per_unit,
                    lbc_per_step = EXCLUDED.lbc_per_step,
                    speed_min_kmh = EXCLUDED.speed_min_kmh,
                    speed_max_kmh = EXCLUDED.speed_max_kmh,
                    metadata = EXCLUDED.metadata,
                    updated_at = now()
                RETURNING id
                """,
                BASE_OFFCHAIN_NFT_SLUG,
                BASE_OFFCHAIN_NFT_TITLE,
                BASE_OFFCHAIN_NFT_KIND,
                base_energy_units_dec,
                steps_per_unit,
                base_lbc_per_step_dec,
                base_speed_min_dec,
                base_speed_max_dec,
                base_template_metadata_json,
            )
            base_template_id = base_template_row["id"]
            await c.execute(
                """
                UPDATE users
                   SET active_nft_template_id = $1,
                       energy_units = $2,
                       steps_per_unit = $3,
                       lbc_per_step = $4,
                       speed_min_kmh = $5,
                       speed_max_kmh = $6,
                       energy_max = $7,
                       energy_left = LEAST(energy_left, $7),
                       updated_at = now()
                 WHERE active_nft_template_id IS DISTINCT FROM $1
                    OR energy_units IS DISTINCT FROM $2
                    OR steps_per_unit IS DISTINCT FROM $3
                    OR lbc_per_step IS DISTINCT FROM $4
                    OR speed_min_kmh IS DISTINCT FROM $5
                    OR speed_max_kmh IS DISTINCT FROM $6
                    OR energy_max IS DISTINCT FROM $7
                """,
                base_template_id,
                base_energy_units_dec,
                steps_per_unit,
                base_lbc_per_step_dec,
                base_speed_min_dec,
                base_speed_max_dec,
                base_energy_limit_steps,
            )
'''

ENSURE_SCHEMA_BLOCK = textwrap.indent(textwrap.dedent(ENSURE_SCHEMA_BODY).strip("\n"), "    ") + "\n"


def strip_existing_const_block(source: str) -> str:
    if "BASE_OFFCHAIN_NFT_SLUG" not in source:
        return source
    start = source.index("BASE_OFFCHAIN_NFT_SLUG")
    meta_start = source.find("{", start)
    if meta_start == -1:
        raise SystemExit("Не удалось найти начало словаря BASE_OFFCHAIN_NFT_METADATA")
    brace_depth = 0
    pos = meta_start
    while pos < len(source):
        ch = source[pos]
        if ch == "{":
            brace_depth += 1
        elif ch == "}":
            brace_depth -= 1
            if brace_depth == 0:
                pos += 1
                break
        pos += 1
    while pos < len(source) and source[pos] == "\n":
        pos += 1
    return source[:start] + source[pos:]


def main() -> None:
    repo_root = Path(__file__).resolve().parent
    db_path = repo_root / "db.py"
    if not db_path.exists():
        raise SystemExit("Не найден db.py рядом со скриптом")
    backup_path = db_path.with_name(db_path.name + ".bak")
    shutil.copy2(db_path, backup_path)

    text = db_path.read_text(encoding="utf-8")
    text = strip_existing_const_block(text)

    anchor = "DB_DSN ="
    try:
        anchor_idx = text.index(anchor)
    except ValueError as exc:
        raise SystemExit("Не найдено объявление DB_DSN в db.py") from exc
    insert_pos = text.find("\n", anchor_idx)
    if insert_pos == -1:
        insert_pos = len(text)
    else:
        insert_pos += 1
    suffix = text[insert_pos:].lstrip("\n")
    text = text[:insert_pos] + "\n" + CONST_BLOCK + suffix

    ensure_start = text.find("    async def ensure_schema(self):")
    if ensure_start == -1:
        raise SystemExit("Не удалось найти ensure_schema в db.py")
    marker = "    # === служебные ==="
    ensure_end = text.find(marker, ensure_start)
    if ensure_end == -1:
        raise SystemExit("Не удалось найти маркер '# === служебные ==='")
    text = text[:ensure_start] + ENSURE_SCHEMA_BLOCK + text[ensure_end:]

    db_path.write_text(text, encoding="utf-8")
    print(f"Готово: db.py обновлён, резервная копия сохранена в {backup_path.name}")


if __name__ == "__main__":
    main()
