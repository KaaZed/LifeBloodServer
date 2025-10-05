import asyncio
import json
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable

CURRENT_DIR = Path(__file__).resolve().parent
POSSIBLE_ROOTS = (CURRENT_DIR, CURRENT_DIR.parent)
for candidate in POSSIBLE_ROOTS:
    if (candidate / "db.py").exists():
        PROJECT_ROOT = candidate
        break
else:
    PROJECT_ROOT = CURRENT_DIR

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db import LifeBloodDB

DATA_FILE = PROJECT_ROOT / "members old.json"


def load_old_balances(path: Path = DATA_FILE) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


async def main_async() -> None:
    records = load_old_balances()
    db = LifeBloodDB()
    updated_count = 0
    skipped_count = 0

    try:
        await db.ensure_schema()
        await db.connect()
        async with db.pool.acquire() as conn:
            for item in records:
                tg_id = item.get("tg_id")
                if not tg_id:
                    skipped_count += 1
                    continue

                balance = item.get("balance") or {}
                total_raw = balance.get("lbc")
                today_raw = item.get("lbc")
                if total_raw is None and today_raw is None:
                    skipped_count += 1
                    continue

                try:
                    total_lbc = Decimal(str(total_raw if total_raw is not None else 0))
                    today_lbc = Decimal(str(today_raw if today_raw is not None else 0))
                    user_id = int(tg_id)
                except (InvalidOperation, ValueError):
                    skipped_count += 1
                    continue

                username = item.get("tg") or None
                if username:
                    username = username.strip() or None

                await conn.execute(
                    """
                    INSERT INTO users (user_id, username, total_lbc, today_lbc, updated_at)
                    VALUES ($1, $2, $3, $4, now())
                    ON CONFLICT (user_id) DO UPDATE
                    SET total_lbc = EXCLUDED.total_lbc,
                        today_lbc = EXCLUDED.today_lbc,
                        updated_at = now(),
                        username = EXCLUDED.username
                    """,
                    user_id,
                    username,
                    total_lbc,
                    today_lbc,
                )
                updated_count += 1
    finally:
        await db.close()
        print(
            "Импорт завершён. Обновлено записей: {updated}. Пропущено записей: {skipped}.".format(
                updated=updated_count,
                skipped=skipped_count,
            )
        )


if __name__ == "__main__":
    asyncio.run(main_async())
