"""Расширенная диагностика окружения LifeBlood."""
from __future__ import annotations

import asyncio
import os
import platform
import socket
import ssl
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, List, Optional

import asyncpg
import httpx
import psutil
from dotenv import load_dotenv

load_dotenv()


@dataclass
class CheckResult:
    name: str
    ok: bool
    details: str

    def display(self) -> None:
        status = "OK" if self.ok else "FAIL"
        print(f"[{status}] {self.name}\n{self.details}\n")


def format_exception(exc: Exception) -> str:
    return f"{exc.__class__.__name__}: {exc}"


def check_env_vars(required: Iterable[str]) -> CheckResult:
    missing: List[str] = []
    masked: List[str] = []
    for key in required:
        value = os.getenv(key)
        if not value:
            missing.append(key)
            continue
        if len(value) <= 8:
            masked_value = value
        else:
            masked_value = value[:4] + "..." + value[-4:]
        masked.append(f"{key}={masked_value}")
    if missing:
        return CheckResult(
            "Переменные окружения",
            False,
            "Не найдены: " + ", ".join(missing),
        )
    return CheckResult("Переменные окружения", True, "\n".join(masked))


def check_dns(hosts: Iterable[str]) -> List[CheckResult]:
    results: List[CheckResult] = []
    for host in hosts:
        try:
            infos = socket.getaddrinfo(host, None)
        except Exception as exc:  # noqa: BLE001
            results.append(
                CheckResult(
                    f"DNS: {host}",
                    False,
                    format_exception(exc),
                )
            )
            continue
        addresses = sorted({info[4][0] for info in infos})
        details = "\n".join(addresses) if addresses else "Адресов не найдено"
        results.append(CheckResult(f"DNS: {host}", bool(addresses), details))
    return results


def check_tcp_connectivity(host: str, port: int, timeout: float = 3.0) -> CheckResult:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            pass
    except Exception as exc:  # noqa: BLE001
        return CheckResult(
            f"TCP {host}:{port}",
            False,
            format_exception(exc),
        )
    return CheckResult(f"TCP {host}:{port}", True, "Соединение установлено")


def check_system_info() -> str:
    info_lines = [
        f"Время: {datetime.now(timezone.utc).isoformat()}",
        f"Python: {platform.python_version()}",
        f"Платформа: {platform.platform()}",
    ]
    return "\n".join(info_lines)


async def check_telegram(token: Optional[str]) -> CheckResult:
    if not token:
        return CheckResult(
            "Telegram API",
            False,
            "Переменная TELEGRAM_BOT_TOKEN не задана",
        )
    try:
        async with httpx.AsyncClient(timeout=10.0, verify=ssl.create_default_context()) as client:
            response = await client.get(
                f"https://api.telegram.org/bot{token}/getMe",
                follow_redirects=True,
            )
    except Exception as exc:  # noqa: BLE001
        return CheckResult("Telegram API", False, format_exception(exc))
    return CheckResult(
        "Telegram API",
        response.status_code == 200,
        f"HTTP {response.status_code}: {response.text[:500]}",
    )


async def check_database(dsn: Optional[str]) -> CheckResult:
    if not dsn:
        return CheckResult("PostgreSQL", False, "Переменная DB_DSN не задана")
    try:
        conn = await asyncpg.connect(dsn, timeout=5.0)
    except Exception as exc:  # noqa: BLE001
        return CheckResult("PostgreSQL", False, format_exception(exc))
    try:
        row = await conn.fetchrow("SELECT version() AS ver, current_schema AS schema")
    except Exception as exc:  # noqa: BLE001
        await conn.close()
        return CheckResult("PostgreSQL", False, format_exception(exc))
    await conn.close()
    details = "\n".join(
        f"{key}: {value}" for key, value in row.items() if value is not None
    )
    return CheckResult("PostgreSQL", True, details)


def check_listening_ports() -> CheckResult:
    listeners: List[str] = []
    try:
        for conn in psutil.net_connections(kind="inet"):
            if conn.status != psutil.CONN_LISTEN:
                continue
            ip = getattr(conn.laddr, "ip", conn.laddr[0])
            port = getattr(conn.laddr, "port", conn.laddr[1])
            pid = conn.pid or 0
            try:
                name = psutil.Process(pid).name() if pid else "?"
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                name = "?"
            listeners.append(f"{ip}:{port} -> PID {pid} ({name})")
    except psutil.AccessDenied as exc:
        return CheckResult("Слушающие порты", False, format_exception(exc))
    except Exception as exc:  # noqa: BLE001
        return CheckResult("Слушающие порты", False, format_exception(exc))
    if not listeners:
        return CheckResult("Слушающие порты", False, "Нет приложений в состоянии LISTEN")
    listeners.sort()
    return CheckResult("Слушающие порты", True, "\n".join(listeners))


async def main() -> None:
    print("=== СИСТЕМНАЯ ИНФОРМАЦИЯ ===")
    print(check_system_info())

    required = [
        "TELEGRAM_BOT_TOKEN",
        "DB_DSN",
        "WEBHOOK_URL",
        "DOMAIN",
    ]
    check_env_vars(required).display()

    print("=== СЕТЬ ===")
    dns_results = check_dns(["db", "postgres", "api.telegram.org", "lifeblood.ru"])
    for result in dns_results:
        result.display()

    tcp_checks = [
        check_tcp_connectivity("db", 5432),
        check_tcp_connectivity("localhost", 5432),
        check_tcp_connectivity("api.telegram.org", 443),
    ]
    for check in tcp_checks:
        check.display()

    print("=== ВНЕШНИЕ СЕРВИСЫ ===")
    telegram_result = await check_telegram(os.getenv("TELEGRAM_BOT_TOKEN"))
    telegram_result.display()

    db_result = await check_database(os.getenv("DB_DSN"))
    db_result.display()

    print("=== ЛОКАЛЬНЫЕ ПОРТЫ ===")
    check_listening_ports().display()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Прервано пользователем")
