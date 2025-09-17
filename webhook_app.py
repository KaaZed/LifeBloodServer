import os, json, asyncio, time
from typing import Any, Dict, Tuple
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from dotenv import load_dotenv
from logger import info, err
from db import LifeBloodDB
from tg_api import send_text, edit_text, delete_message

load_dotenv()

APP_VER = "rescue_118"

app = FastAPI()

# === DB ===
DSN = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_DSN") or os.getenv("DB_DSN") or ""
db = LifeBloodDB(DSN) if DSN else None

@app.on_event("startup")
async def _startup():
    if not db:
        err("[db] DSN missing")
        return
    try:
        await db.connect()
        if hasattr(db, "ensure_schema"):
            await db.ensure_schema()
        info("[startup] ok")
    except Exception as e:
        err(f"[startup] db connect error: {e}")
    finally:
        token_present = bool(os.getenv("TELEGRAM_BOT_TOKEN"))
        dsn_present = bool(os.getenv("DB_DSN"))
        info(f"[startup] TELEGRAM_BOT_TOKEN present: {token_present}")
        info(f"[startup] DB_DSN present: {dsn_present}")

@app.get("/ping")
async def ping():
    return PlainTextResponse(f"ok {APP_VER}")

# === Dashboard state ===
_DASH: Dict[int, Dict[str, Any]] = {}
_DASH_THROTTLE = int(os.getenv("DASH_THROTTLE_SEC") or os.getenv("DASHBOARD_THROTTLE_SEC") or 10)

def _now() -> float:
    try:
        return asyncio.get_event_loop().time()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.time()

def _fmt_lbc(x: Any) -> str:
    try:
        return f"{float(x):.5f}"
    except Exception:
        return "0.00000"

def _fi(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return 0

def _ff(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0

def _sig(stats: Dict[str, Any]) -> Tuple[int, int, float, float, int, int, str]:
    s = stats or {}
    return (
        _fi(s.get("today_steps")),
        _fi(s.get("total_steps")),
        _ff(s.get("today_lbc")),
        _ff(s.get("total_lbc")),
        _fi(s.get("energy_left")),
        _fi(s.get("energy_max")),
        (s.get("reason_if_not_counted") or "").strip(),
    )

def _dash_text(stats: Dict[str, Any]) -> str:
    s = stats or {}
    reason = (s.get("reason_if_not_counted") or "").strip()
    line_reason = f"\\n⛔ <i>{reason}</i>" if reason else ""
    return (
        "🩸 <b>LifeBlood — Дашборд</b>\\n"
        f"👣 Шаги сегодня: <b>{int(s.get('today_steps',0))}</b>\\n"
        f"💧 LBC сегодня: <b>{_fmt_lbc(s.get('today_lbc',0))}</b>\\n"
        f"📈 Шаги всего: <b>{int(s.get('total_steps',0))}</b>\\n"
        f"💰 LBC всего: <b>{_fmt_lbc(s.get('total_lbc',0))}</b>\\n"
        f"🔋 Энергия: <b>{int(s.get('energy_left',0))}/{int(s.get('energy_max',0))}</b>" + line_reason
    )

async def _send_new(user_id: int, chat_id: int, text: str, sig):
    ok, resp = await send_text(chat_id, text, disable_web_page_preview=True)
    if not ok:
        err(f"[dash] send fail: {resp}")
        return
    mid = int(resp.get("result", {}).get("message_id") or 0)
    if not mid:
        return
    _DASH[user_id] = {"msg_id": mid, "chat_id": chat_id, "last_ts": _now(), "sig": sig}
    if db and hasattr(db, "save_dashboard_msg_id"):
        try:
            await db.save_dashboard_msg_id(user_id, chat_id, mid)
        except Exception as e:
            err(f"[dash] save_dashboard_msg_id error: {e}")
    info(f"[dash] send ok chat:{chat_id} msg:{mid}")

async def _ensure_dashboard(user_id: int, chat_id: int, stats: Dict[str, Any], is_new_session: bool) -> None:
    text = _dash_text(stats)
    sig_curr = _sig(stats)

    state = _DASH.get(user_id) or {}
    msg_id = state.get("msg_id")
    last_ts = float(state.get("last_ts") or 0.0)
    last_sig = state.get("sig")
    state_chat_id = int(state.get("chat_id") or chat_id)

    if is_new_session:
        # удалить старый дашборд (best effort)
        if msg_id:
            try:
                ok, _ = await delete_message(state_chat_id, msg_id)
                info(f"[dash] delete old msg:{msg_id} ok={ok}")
            except Exception as e:
                err(f"[dash] delete exception: {e}")
        elif db and hasattr(db, "get_dashboard_target"):
            try:
                db_chat, db_msg = await db.get_dashboard_target(user_id)
                if db_msg:
                    ok, _ = await delete_message(int(db_chat), int(db_msg))
                    info(f"[dash] delete old (db) msg:{db_msg} ok={ok}")
            except Exception as e:
                err(f"[dash] delete(db) exception: {e}")
        await _send_new(user_id, chat_id, text, sig_curr)
        return

    # обычные апдейты
    if _now() - last_ts < _DASH_THROTTLE:
        info(f"[dash] throttle user:{user_id}")
        return

    if not msg_id:
        # пробуем восстановить из БД
        if db and hasattr(db, "get_dashboard_target"):
            try:
                db_chat, db_msg = await db.get_dashboard_target(user_id)
                if db_msg:
                    msg_id = int(db_msg); state_chat_id = int(db_chat or chat_id)
                    _DASH[user_id] = {"msg_id": msg_id, "chat_id": state_chat_id, "last_ts": 0.0, "sig": last_sig}
                    info(f"[dash] restored msg_id={msg_id} from DB")
            except Exception as e:
                err(f"[dash] restore db error: {e}")
        if not msg_id:
            await _send_new(user_id, chat_id, text, sig_curr)
            return

    if last_sig == sig_curr:
        _DASH[user_id] = {"msg_id": msg_id, "chat_id": state_chat_id, "last_ts": _now(), "sig": sig_curr}
        info(f"[dash] no content change → skip edit")
        return

    ok, resp = await edit_text(state_chat_id, msg_id, text, disable_web_page_preview=True)
    if ok:
        _DASH[user_id] = {"msg_id": msg_id, "chat_id": state_chat_id, "last_ts": _now(), "sig": sig_curr}
        return
    desc = str((resp or {}).get("description", "")).lower()
    code = (resp or {}).get("error_code")
    if code == 400 and "message to edit not found" in desc:
        _DASH[user_id] = {"msg_id": None, "chat_id": state_chat_id, "last_ts": _now(), "sig": sig_curr}
        info("[dash] msg not found → wait new session")
        return
    if code == 400 and "not modified" in desc:
        _DASH[user_id] = {"msg_id": msg_id, "chat_id": state_chat_id, "last_ts": _now(), "sig": sig_curr}
        info("[dash] edit not-modified → noop")
        return
    err(f"[dash] edit failed: {resp}")

def _extract(d: Dict[str, Any], path, default=None):
    cur = d
    for k in path:
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        else:
            return default
    return cur

@app.post("/webhook")
async def webhook(request: Request):
    try:
        update = await request.json()
    except Exception:
        body = await request.body()
        try:
            update = json.loads(body.decode("utf-8"))
        except Exception as e:
            err(f"[webhook] bad json: {e}")
            return JSONResponse({"ok": False})

    msg = update.get("edited_message") or update.get("message") or {}
    if not msg:
        return JSONResponse({"ok": True})

    chat_id = int(_extract(msg, ["chat","id"], 0) or 0)
    user_id = int(_extract(msg, ["from","id"], 0) or 0)
    username = _extract(msg, ["from","username"])

    text = (msg.get("text") or "").strip()
    if text.startswith("/start"):
        ref = None
        parts = text.split(maxsplit=1)
        if len(parts) == 2 and parts[1].isdigit():
            ref = int(parts[1])
        try:
            if db and hasattr(db, "register_user"):
                await db.register_user(user_id, username, referrer_id=ref)
            await send_text(chat_id, "Привет! Отправь Live Location, и я начну учитывать шаги.")
            info("[webhook] /start ok")
        except Exception as e:
            err(f"[webhook] /start exception: {e}")
        return JSONResponse({"ok": True})

    if "location" in msg:
        loc = msg.get("location") or {}
        lat = float(loc.get("latitude"))
        lon = float(loc.get("longitude"))
        ts = int(msg.get("date") or int(time.time()))
        live_period = loc.get("live_period")
        is_new_session = bool(live_period and "edit_date" not in msg)

        try:
            if db and hasattr(db, "process_location"):
                # ВАЖНО: передаём epoch ts (int), чтобы не было конфликта типов в БД
                await db.process_location(user_id, username, ts=ts, lat=lat, lon=lon,
                                          accuracy=loc.get("horizontal_accuracy"),
                                          heading=loc.get("heading"), live_period=live_period,
                                          chat_id=chat_id)
                stats = await db.stats(user_id) if hasattr(db, "stats") else {}
            else:
                stats = {}
            await _ensure_dashboard(user_id, chat_id, stats or {}, is_new_session)
            info("[webhook] location ok")
        except Exception as e:
            err(f"[webhook] location exception: {e}")
        return JSONResponse({"ok": True})

    return JSONResponse({"ok": True})
