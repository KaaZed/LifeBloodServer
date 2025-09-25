import os, json, asyncio, time
from typing import Any, Dict, Tuple
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from dotenv import load_dotenv
from logger import info, err
from db import LifeBloodDB
from tg_api import send_text, edit_text, delete_message
from step_config import (
    STEP_LENGTH_METERS,
    SPEED_MIN_KMH,
    SPEED_MAX_KMH,
    LBC_PER_STEP,
    REF_LBC_PER_STEP,
    GPS_MAX_ACCURACY_METERS,
    DAILY_ENERGY_STEPS,
)

load_dotenv()

APP_VER = "rescue_118"

app = FastAPI()

# === DB ===
DSN = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_DSN") or os.getenv("DB_DSN") or ""
db = LifeBloodDB(DSN) if DSN else None

@app.on_event("startup")
async def _startup():
    token_present = bool(os.getenv("TELEGRAM_BOT_TOKEN"))
    dsn_present = bool(os.getenv("DB_DSN"))

    if not db:
        err("[db] DSN missing")
        info(f"[startup] TELEGRAM_BOT_TOKEN present: {token_present}")
        info(f"[startup] DB_DSN present: {dsn_present}")
        return

    try:
        max_attempts = int(os.getenv("DB_CONNECT_RETRIES", "10"))
    except ValueError:
        max_attempts = 10
    max_attempts = max(1, max_attempts)

    try:
        retry_delay = float(os.getenv("DB_CONNECT_RETRY_DELAY_SEC", "3"))
    except ValueError:
        retry_delay = 3.0
    retry_delay = max(0.5, retry_delay)

    for attempt in range(1, max_attempts + 1):
        try:
            await db.connect()
            if hasattr(db, "ensure_schema"):
                await db.ensure_schema()
            info(f"[startup] db ready (attempt {attempt}/{max_attempts})")
            break
        except Exception as e:
            err(f"[startup] db connect error (attempt {attempt}/{max_attempts}): {e}")
            if attempt == max_attempts:
                err("[startup] giving up on initial db connect; will retry lazily on demand")
                break
            await asyncio.sleep(retry_delay)

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

def _sig(stats: Dict[str, Any]) -> Tuple[str, ...]:
    s = stats or {}
    today_steps = str(_fi(s.get("today_steps")))
    total_steps = str(_fi(s.get("total_steps")))
    today_lbc = _fmt_lbc(s.get("today_lbc"))
    total_lbc = _fmt_lbc(s.get("total_lbc"))
    energy_left = max(_fi(s.get("energy_left")), 0)
    energy_max_raw = max(_fi(s.get("energy_max")), 0)
    energy_max = energy_max_raw or int(DAILY_ENERGY_STEPS)
    reason = (s.get("reason_if_not_counted") or "").strip()
    return (
        today_steps,
        total_steps,
        today_lbc,
        total_lbc,
        str(energy_left),
        str(energy_max),
        reason,
        f"{STEP_LENGTH_METERS:.2f}",
        f"{SPEED_MIN_KMH:.2f}",
        f"{SPEED_MAX_KMH:.2f}",
        f"{GPS_MAX_ACCURACY_METERS:.2f}",
        f"{LBC_PER_STEP:.5f}",
        f"{REF_LBC_PER_STEP:.5f}",
        str(int(DAILY_ENERGY_STEPS)),
    )

def _dash_text(stats: Dict[str, Any]) -> str:
    s = stats or {}
    today_steps = _fi(s.get("today_steps"))
    total_steps = _fi(s.get("total_steps"))
    today_lbc = _fmt_lbc(s.get("today_lbc"))
    total_lbc = _fmt_lbc(s.get("total_lbc"))
    energy_left = max(_fi(s.get("energy_left")), 0)
    energy_max_raw = max(_fi(s.get("energy_max")), 0)
    energy_max = energy_max_raw or int(DAILY_ENERGY_STEPS)
    reason = (s.get("reason_if_not_counted") or "").strip()

    reason_line = f"\n⛔ <i>{reason}</i>" if reason else ""
    energy_line = f"🔋 Энергия: <b>{energy_left}/{energy_max}</b> шагов" + reason_line
    norms_line = (
        "⚙️ Нормы: "
        f"шаг {STEP_LENGTH_METERS:.2f}м · "
        f"скорость {SPEED_MIN_KMH:.0f}-{SPEED_MAX_KMH:.0f}км/ч · "
        f"GPS ≤ {GPS_MAX_ACCURACY_METERS:.0f}м · "
        f"лимит {int(DAILY_ENERGY_STEPS)} шагов/день"
    )
    tariff_line = f"💸 Тариф: {LBC_PER_STEP:.5f} LBC/шаг (+{REF_LBC_PER_STEP:.5f} реф.)"

    return (
        "🩸 <b>LifeBlood</b>"
        f"👣 Шаги сегодня: <b>{today_steps}</b>"
        f"💧 LBC сегодня: <b>{today_lbc}</b>"
        f"📈 Шаги всего: <b>{total_steps}</b>"
        f"💰 LBC всего: <b>{total_lbc}</b>"
        f"{energy_line}"
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
