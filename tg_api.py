import os, asyncio, httpx
from typing import Any, Dict, Tuple
from logger import info, err

def _token() -> str|None:
    return (os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN") or "").strip() or None

def _api(method: str) -> str:
    t = _token()
    return f"https://api.telegram.org/bot{t}/{method}"

async def _post(method: str, payload: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    t = _token()
    if not t:
        err("[tg] no TELEGRAM_BOT_TOKEN in env")
        return False, {"ok": False, "error": "no_token"}
    url = _api(method)
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15, connect=5)) as cli:
            r = await cli.post(url, data=payload)
            data: Dict[str, Any] = {}
            try:
                data = r.json()
            except Exception:
                data = {"ok": False, "text": r.text}
            ok = (r.status_code == 200) and bool(data.get("ok"))
            # 'message is not modified' = успех для editMessageText
            if not ok and method == "editMessageText":
                desc = str(data.get("description", "")).lower()
                if "not modified" in desc:
                    info("[tg] editMessageText → not modified (no-op)")
                    return True, {"ok": True, "result": {"not_modified": True}}
            if ok:
                info(f"[tg] {method} ok")
            else:
                err(f"[tg] {method} fail {r.status_code}: {data}")
            return ok, data
    except Exception as e:
        err(f"[tg] {method} exception: {e}")
        return False, {"ok": False, "error": str(e)}

async def send_text(chat_id: int, text: str, **kwargs) -> Tuple[bool, Dict[str, Any]]:
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"} | kwargs
    info(f"[tg] send_text → chat:{chat_id}, len:{len(text)}")
    return await _post("sendMessage", payload)

async def edit_text(chat_id: int, message_id: int, text: str, **kwargs) -> Tuple[bool, Dict[str, Any]]:
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": "HTML"} | kwargs
    info(f"[tg] edit_text → chat:{chat_id}, msg:{message_id}, len:{len(text)}")
    return await _post("editMessageText", payload)

async def delete_message(chat_id: int, message_id: int) -> Tuple[bool, Dict[str, Any]]:
    payload = {"chat_id": chat_id, "message_id": message_id}
    info(f"[tg] delete_message → chat:{chat_id}, msg:{message_id}")
    return await _post("deleteMessage", payload)
