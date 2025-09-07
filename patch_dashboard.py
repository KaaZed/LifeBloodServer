from pathlib import Path

path = Path("webhook_app.py")
src = path.read_text(encoding="utf-8")

src = src.replace(
    'msg = update.get("message") or update.get("edited_message") or {}',
    'msg = update.get("edited_message") or update.get("message") or {}'
)

src = src.replace(
    'live_period = loc.get("live_period")\n        is_new_session = bool(update.get("message") and live_period)',
    'live_period = loc.get("live_period")\n        is_new_session = bool(live_period and "edit_date" not in msg)'
)

src = src.replace(
    '        if not msg_id:\n            info(f"[dash] no msg in session → skip (wait new session)")\n            return',
    '        if not msg_id:\n            await _send_new(user_id, chat_id, text, sig_curr)\n            return'
)

path.write_text(src, encoding="utf-8")
print("patch applied")
