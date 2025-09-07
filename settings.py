# settings.py — single source of truth for env + dynamic app settings
import os
from pathlib import Path
from typing import Dict

# --- .env loader (simple, no external deps)
def _load_env_file() -> dict:
    env = {}
    p = Path(__file__).resolve().parent / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    # allow process env override
    for k in ("DB_DSN","DATABASE_URL","POSTGRES_DSN","TELEGRAM_BOT_TOKEN","BOT_USERNAME","ADMIN_API_TOKEN"):
        if k in os.environ:
            env[k] = os.environ[k]
    return env

_ENV = _load_env_file()

# required keys
DB_DSN = _ENV.get("DB_DSN") or _ENV.get("DATABASE_URL") or _ENV.get("POSTGRES_DSN")
TELEGRAM_BOT_TOKEN = _ENV.get("TELEGRAM_BOT_TOKEN")
BOT_USERNAME = _ENV.get("BOT_USERNAME")
ADMIN_API_TOKEN = _ENV.get("ADMIN_API_TOKEN")

_missing = [k for k,v in {
    "DB_DSN":DB_DSN, "TELEGRAM_BOT_TOKEN":TELEGRAM_BOT_TOKEN,
    "BOT_USERNAME":BOT_USERNAME, "ADMIN_API_TOKEN":ADMIN_API_TOKEN
}.items() if not v]

if _missing:
    raise RuntimeError(f"Missing required .env keys: {', '.join(_missing)}")

# --- dynamic app settings from DB (app_settings)
# usage:
#   async with pool.acquire() as c:
#       app_cfg = await load_app_settings(c)
#       cluster = int(app_cfg.get("CLUSTER_RADIUS_METERS","100"))
async def load_app_settings(conn) -> Dict[str,str]:
    rows = await conn.fetch("SELECT key, value FROM app_settings")
    return {r["key"]: r["value"] for r in rows}
