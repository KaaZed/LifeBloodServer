import os
import asyncio
from pathlib import Path

from dotenv import load_dotenv

from logger import info, err
from db import LifeBloodDB
from tg_api import send_text

MESSAGE_PATH = Path(__file__).with_name("broadcast_message.txt")
DEFAULT_DELAY = 0.2


async def main() -> None:
    load_dotenv()

    if not MESSAGE_PATH.exists():
        err(f"[broadcast] message file not found: {MESSAGE_PATH}")
        return

    text = MESSAGE_PATH.read_text(encoding="utf-8").strip()
    if not text:
        err("[broadcast] message file is empty")
        return

    db = LifeBloodDB()
    await db.connect()

    try:
        targets = await db.list_broadcast_targets()
        info(f"[broadcast] recipients: {len(targets)}")

        ok_cnt = fail_cnt = skip_cnt = 0
        delay = max(float(os.getenv("BROADCAST_PAUSE_SEC", DEFAULT_DELAY)), 0.0)

        for user_id, chat_id in targets:
            ok, resp = await send_text(chat_id, text, disable_web_page_preview=True)
            if ok:
                ok_cnt += 1
            else:
                code = resp.get("error_code")
                desc = (resp.get("description") or "").lower()
                if code == 403 or "blocked" in desc or "forbidden" in desc:
                    skip_cnt += 1
                    info(f"[broadcast] skip {chat_id}: blocked ({resp})")
                else:
                    fail_cnt += 1
                    err(f"[broadcast] fail {chat_id}: {resp}")
            if delay:
                await asyncio.sleep(delay)

        info(f"[broadcast] done ok={ok_cnt} skip={skip_cnt} fail={fail_cnt}")
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
