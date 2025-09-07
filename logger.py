# logger.py — минимальный логгер для LifeBlood
# Пишет в events.log; используется info() и err()

from __future__ import annotations
import os, sys, threading, time
from pathlib import Path

# путь к файлу логов можно задать через переменную окружения LIFEBLOOD_LOG_PATH
_DEFAULT_LOG_PATH = Path(__file__).resolve().parent / "events.log"
_LOG_PATH = Path(os.environ.get("LIFEBLOOD_LOG_PATH", _DEFAULT_LOG_PATH))
_LOCK = threading.Lock()

def _ts() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

def _write(line: str) -> bool:
    try:
        with _LOCK:
            _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with _LOG_PATH.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        return True
    except Exception as e:
        # не удалось записать в файл — логируем предупреждение в stderr
        try:
            sys.stderr.write(f"[LOGGER WARNING] {e}: {line}\n")
        except Exception:
            pass
        return False

def info(msg: str) -> bool:
    return _write(f"[{_ts()}] [INFO] {msg}")

def err(msg: str) -> bool:
    line = f"[{_ts()}] [ERROR] {msg}"
    success = _write(line)
    try:
        sys.stderr.write(line + "\n")
    except Exception:
        pass
    return success