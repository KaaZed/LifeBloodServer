import asyncio
from decimal import Decimal, InvalidOperation
from pathlib import Path
import json

import asyncpg

from settings import DB_DSN

_QUANT = Decimal("0.00000001")


async def _load_balances() -> tuple[dict[int, Decimal], int, int]:
    source_path = Path(__file__).resolve().parents[1] / "members old.json"
    raw_data = json.loads(source_path.read_text(encoding="utf-8"))

    totals: dict[int, Decimal] = {}
    skipped = 0

    for entry in raw_data:
        tg_id = entry.get("tg_id")
        balance_info = entry.get("balance") if isinstance(entry, dict) else None
        lbc_value = balance_info.get("lbc") if isinstance(balance_info, dict) else None

        if tg_id is None or lbc_value is None:
            skipped += 1
            continue

        try:
            user_id = int(tg_id)
        except (TypeError, ValueError):
            skipped += 1
            continue

        try:
            amount = Decimal(str(lbc_value)).quantize(_QUANT)
        except (InvalidOperation, TypeError, ValueError):
            skipped += 1
            continue

        current = totals.get(user_id)
        if current is None or amount > current:
            totals[user_id] = amount

    return totals, len(raw_data), skipped


async def _upsert_balances(balances: dict[int, Decimal]) -> int:
    if not balances:
        return 0

    if not DB_DSN:
        raise RuntimeError("DB_DSN is not configured")

    pool = await asyncpg.create_pool(dsn=DB_DSN)
    upserted = 0
    async with pool:
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("UPDATE users SET total_lbc = 0 WHERE total_lbc IS NULL")
                query = (
                    "INSERT INTO users (user_id, total_lbc) VALUES ($1, $2) "
                    "ON CONFLICT (user_id) DO UPDATE SET "
                    "total_lbc = GREATEST(users.total_lbc, EXCLUDED.total_lbc), "
                    "updated_at = now()"
                )
                await conn.executemany(query, balances.items())
                upserted = len(balances)
    return upserted


async def main() -> None:
    balances, total, skipped = await _load_balances()
    upserted = await _upsert_balances(balances)

    print(f"Прочитано записей: {total}")
    print(f"Пропущено из-за отсутствия данных: {skipped}")
    print(f"Обновлено/создано записей: {upserted}")


if __name__ == "__main__":
    asyncio.run(main())
