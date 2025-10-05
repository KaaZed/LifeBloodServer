#!/usr/bin/env python3
from pathlib import Path

METHOD_SNIPPET = (
    "\n"
    "    async def list_broadcast_targets(self) -> list[tuple[int, int]]:\n"
    "        await self.connect()\n"
    "        async with self.pool.acquire() as c:\n"
    "            rows = await c.fetch(\n"
    "                \"\"\"\n"
    "                SELECT user_id,\n"
    "                       COALESCE(NULLIF(dashboard_chat_id, 0), user_id) AS chat_id\n"
    "                  FROM users\n"
    "                 ORDER BY user_id\n"
    "                \"\"\"\n"
    "            )\n"
    "\n"
    "        targets: list[tuple[int, int]] = []\n"
    "        for row in rows:\n"
    "            user_id = row[\"user_id\"]\n"
    "            chat_id = row[\"chat_id\"]\n"
    "            if chat_id is None:\n"
    "                continue\n"
    "            try:\n"
    "                targets.append((int(user_id), int(chat_id)))\n"
    "            except (TypeError, ValueError):\n"
    "                continue\n"
    "        return targets\n"
    "\n"
)

def main() -> None:
    path = Path("db.py")
    if not path.exists():
        raise SystemExit("Файл db.py не найден — запускать нужно из корня проекта.")

    text = path.read_text(encoding="utf-8")
    if "async def list_broadcast_targets" in text:
        print("Метод list_broadcast_targets уже присутствует, изменений не требуется.")
        return

    marker = "    async def ensure_schema"
    idx = text.find(marker)
    if idx == -1:
        raise SystemExit("Не удалось найти место вставки (async def ensure_schema).")

    updated = text[:idx] + METHOD_SNIPPET + text[idx:]
    path.write_text(updated, encoding="utf-8")
    print("Метод list_broadcast_targets добавлен в db.py.")

if __name__ == "__main__":
    main()
