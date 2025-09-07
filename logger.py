# logger.py — минимальный логгер для LifeBlood
# Пишет в events.log; используется info() и err()

from __future__ import annotations
import os, sys, threading, time
from pathlib import Path

_LOG_PATH = Path(__file__).resolve().parent / "events.log"
_LOCK = threading.Lock()

def _ts() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

def _write(line: str) -> None:
    try:
        with _LOCK:
            with _LOG_PATH.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
    except Exception:
        # если почему-то не удалось писать в файл — дублируем в stderr
        try:
            sys.stderr.write(line + "\n")
        except Exception:
            pass

def info(msg: str) -> None:
    _write(f"[{_ts()}] [INFO] {msg}")

def err(msg: str) -> None:
    _write(f"[{_ts()}] [ERROR] {msg}")
    try:
        sys.stderr.write(f"[ERROR] {msg}\n")
    except Exception:
        pass
