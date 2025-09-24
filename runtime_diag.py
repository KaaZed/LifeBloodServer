"""Расширенная диагностика окружения LifeBlood."""
from __future__ import annotations

import asyncio
import os
import platform
import socket
import ssl
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, List, Mapping, Optional, Set, Tuple
from urllib.parse import quote, urlparse

import asyncpg
import httpx
import psutil
from dotenv import load_dotenv, dotenv_values

load_dotenv()


DEFAULT_PG_PORT = 5432
DEFAULT_DB_HOST_ALIASES: Set[str] = {"db", "postgres"}


@dataclass(frozen=True)
class DsnInfo:
    raw: str
    scheme: str
    user: Optional[str]
    password: Optional[str]
    host: Optional[str]
    port: int
    database: Optional[str]
    query: str

    def as_dsn(self, override_host: Optional[str] = None) -> str:
        host = override_host or self.host or ""
        if ":" in host and not host.startswith("["):
            host_part = f"[{host}]"
        else:
            host_part = host
        userinfo = ""
        if self.user:
            userinfo += quote(self.user)
            if self.password:
                userinfo += ":" + quote(self.password)
            userinfo += "@"
        port_part = f":{self.port}" if host_part else ""
        path_part = f"/{self.database}" if self.database else ""
        query_part = f"?{self.query}" if self.query else ""
        return f"{self.scheme}://{userinfo}{host_part}{port_part}{path_part}{query_part}"


@dataclass(frozen=True)
class DbAttempt:
    label: str
    dsn: str
    host: Optional[str]
    is_fallback: bool


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


def normalize_pg_scheme(raw_scheme: str) -> str:
    if raw_scheme in {"postgres", "postgresql"}:
        return "postgresql"
    return raw_scheme or "postgresql"


def parse_db_dsn(dsn: str) -> Optional[DsnInfo]:
    try:
        parsed = urlparse(dsn)
    except Exception:  # noqa: BLE001
        return None
    scheme = normalize_pg_scheme(parsed.scheme)
    database = parsed.path.lstrip("/") if parsed.path else None
    host = parsed.hostname
    port = parsed.port or DEFAULT_PG_PORT
    return DsnInfo(
        raw=dsn,
        scheme=scheme,
        user=parsed.username,
        password=parsed.password,
        host=host,
        port=port,
        database=database if database else None,
        query=parsed.query,
    )


def _mask_value(raw: str) -> str:
    if len(raw) <= 8:
        return raw
    return raw[:4] + "..." + raw[-4:]


def check_env_vars(
    required: Iterable[str],
    file_values: Mapping[str, Optional[str]] | None = None,
) -> List[CheckResult]:
    missing: List[str] = []
    present: List[str] = []
    for key in required:
        value = os.getenv(key)
        if not value:
            missing.append(key)
            continue
        present.append(f"{key}={_mask_value(value)}")

    results: List[CheckResult] = []
    if missing:
        details = ["Не найдены: " + ", ".join(missing)]
        if present:
            details.append("Установлены:\n" + "\n".join(present))
        results.append(CheckResult("Переменные окружения", False, "\n".join(details)))
    else:
        results.append(CheckResult("Переменные окружения", True, "\n".join(present)))

    if file_values:
        overrides: List[str] = []
        for key in required:
            file_val = file_values.get(key)
            env_val = os.getenv(key)
            if not file_val or not env_val:
                continue
            if env_val == file_val:
                continue
            hint_parts: List[str] = []
            if key == "DB_DSN":
                env_info = parse_db_dsn(env_val)
                file_info = parse_db_dsn(file_val)
                env_host = env_info.host if env_info else None
                file_host = file_info.host if file_info else None
                if env_host or file_host:
                    hint_parts.append(
                        f"хост в окружении: {env_host or '<не указан>'}; в .env: {file_host or '<не указан>'}"
                    )
            hint = "; ".join(hint_parts)
            if hint:
                overrides.append(
                    f"{key}: активное значение {_mask_value(env_val)} отличается от .env {_mask_value(file_val)} ({hint})"
                )
            else:
                overrides.append(
                    f"{key}: активное значение {_mask_value(env_val)} отличается от .env {_mask_value(file_val)}"
                )
        if overrides:
            results.append(
                CheckResult(
                    "Конфликт значений с .env",
                    False,
                    "\n".join(overrides),
                )
            )

    return results


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


def prepare_network_targets(dsn_value: Optional[str]) -> Tuple[List[str], List[Tuple[str, int]], Optional[DsnInfo]]:
    info = parse_db_dsn(dsn_value) if dsn_value else None
    dns_hosts: Set[str] = {"api.telegram.org", "lifeblood.ru"}
    tcp_targets: Set[Tuple[str, int]] = {("api.telegram.org", 443)}
    port = info.port if info else DEFAULT_PG_PORT
    if info and info.host:
        dns_hosts.add(info.host)
        tcp_targets.add((info.host, port))
        if info.host in DEFAULT_DB_HOST_ALIASES:
            fallback_hosts = {"localhost", "127.0.0.1"}
        elif info.host == "localhost":
            fallback_hosts = {"127.0.0.1"}
        elif info.host == "127.0.0.1":
            fallback_hosts = {"localhost"}
        else:
            fallback_hosts = set()
    else:
        fallback_hosts = {"localhost"}
        dns_hosts.update(DEFAULT_DB_HOST_ALIASES)
        tcp_targets.update({("db", port), ("postgres", port)})
    for host in fallback_hosts:
        dns_hosts.add(host)
        tcp_targets.add((host, port))
    ordered_dns = sorted(dns_hosts)
    ordered_tcp = sorted(tcp_targets, key=lambda item: (item[0], item[1]))
    return ordered_dns, ordered_tcp, info


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


async def check_database(dsn: Optional[str], info: Optional[DsnInfo] = None) -> CheckResult:
    if not dsn:
        return CheckResult("PostgreSQL", False, "Переменная DB_DSN не задана")
    info = info or parse_db_dsn(dsn)
    attempts: List[DbAttempt] = []
    if info:
        attempts.append(
            DbAttempt(
                label=f"{info.host or '<не указан>'} (из DB_DSN)",
                dsn=info.as_dsn(),
                host=info.host,
                is_fallback=False,
            )
        )
        if info.host in DEFAULT_DB_HOST_ALIASES:
            for fallback_host in ("localhost", "127.0.0.1"):
                attempts.append(
                    DbAttempt(
                        label=f"{fallback_host} (fallback)",
                        dsn=info.as_dsn(fallback_host),
                        host=fallback_host,
                        is_fallback=True,
                    )
                )
        elif info.host in {"localhost", "127.0.0.1"}:
            alt = "127.0.0.1" if info.host == "localhost" else "localhost"
            attempts.append(
                DbAttempt(
                    label=f"{alt} (fallback)",
                    dsn=info.as_dsn(alt),
                    host=alt,
                    is_fallback=True,
                )
            )
    else:
        primary_dsn = dsn
        attempts.append(
            DbAttempt(
                label="из DB_DSN",
                dsn=primary_dsn,
                host=None,
                is_fallback=False,
            )
        )

    unique_attempts: List[DbAttempt] = []
    seen: Set[str] = set()
    for attempt in attempts:
        if attempt.dsn in seen:
            continue
        seen.add(attempt.dsn)
        unique_attempts.append(attempt)

    errors: List[str] = []
    for attempt in unique_attempts:
        try:
            conn = await asyncpg.connect(attempt.dsn, timeout=5.0)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{attempt.label}: {format_exception(exc)}")
            continue
        try:
            row = await conn.fetchrow("SELECT version() AS ver, current_schema AS schema")
        except Exception as exc:  # noqa: BLE001
            await conn.close()
            return CheckResult("PostgreSQL", False, format_exception(exc))
        await conn.close()
        info_lines: List[str] = []
        host_hint = attempt.host or (info.host if info else None)
        if host_hint:
            suffix = " (fallback)" if attempt.is_fallback else ""
            info_lines.append(f"Хост: {host_hint}{suffix}")
        if info and info.port:
            info_lines.append(f"Порт: {info.port}")
        if info and info.database:
            info_lines.append(f"База: {info.database}")
        if info and info.user:
            info_lines.append(f"Пользователь: {info.user}")
        info_lines.extend(
            f"{key}: {value}" for key, value in row.items() if value is not None
        )
        if errors:
            info_lines.append("")
            info_lines.append("Предыдущие попытки не удались:")
            info_lines.extend(errors)
        return CheckResult("PostgreSQL", True, "\n".join(info_lines))

    if errors:
        return CheckResult("PostgreSQL", False, "\n".join(errors))
    return CheckResult("PostgreSQL", False, "Не удалось установить соединение")


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


def _parse_tcp_target(name: str) -> Tuple[str, Optional[int]]:
    try:
        _, rest = name.split(" ", 1)
    except ValueError:
        return name, None
    if ":" not in rest:
        return rest, None
    host_part, port_part = rest.split(":", 1)
    try:
        return host_part, int(port_part)
    except ValueError:
        return host_part, None


def print_recommendations(
    results: Iterable[CheckResult],
    active_info: Optional[DsnInfo],
    file_info: Optional[DsnInfo],
) -> None:
    hints: List[str] = []

    env_missing = next(
        (result for result in results if result.name == "Переменные окружения" and not result.ok),
        None,
    )
    if env_missing:
        hints.append(
            "Заполни переменные WEBHOOK_URL и DOMAIN в .env (например, WEBHOOK_URL=https://lifeblood.ru/api/webhook, DOMAIN=lifeblood.ru), затем перезапусти сервис."
        )

    dns_fail_hosts: Set[str] = set()
    for result in results:
        if result.name.startswith("DNS: ") and not result.ok and "Temporary failure in name resolution" in result.details:
            dns_fail_hosts.add(result.name.split(": ", 1)[1])

    tcp_fail_hosts: Set[str] = set()
    for result in results:
        if result.name.startswith("TCP ") and not result.ok and "Temporary failure in name resolution" in result.details:
            host, _ = _parse_tcp_target(result.name)
            tcp_fail_hosts.add(host)

    pg_fail = next(
        (
            result
            for result in results
            if result.name == "PostgreSQL" and not result.ok and "Temporary failure in name resolution" in result.details
        ),
        None,
    )

    active_host = active_info.host if active_info else None
    file_host = file_info.host if file_info else None
    if (
        (dns_fail_hosts or tcp_fail_hosts or pg_fail)
        and active_host in DEFAULT_DB_HOST_ALIASES
    ):
        hints.append(
            "Переменная DB_DSN сейчас указывает на контейнерный хост 'db'. Если запускаешь бот без Docker, выполни: 1) printenv DB_DSN; 2) unset DB_DSN; 3) убедись, что в файле .env стоит localhost, затем перезапусти uvicorn."
        )
    elif pg_fail and active_host and active_host not in DEFAULT_DB_HOST_ALIASES:
        hints.append(
            f"База недоступна по хосту {active_host}. Проверь, что PostgreSQL запущен и что порт {active_info.port if active_info else DEFAULT_PG_PORT} открыт (например, sudo systemctl status postgresql)."
        )

    if active_info and file_info and active_info.host != file_info.host:
        hints.append(
            f"Активное значение DB_DSN использует хост {active_info.host or '<нет>'}, а в .env указан {file_info.host or '<нет>'}. Синхронизируй их и перезапусти сервис."
        )

    if hints:
        print("=== ЧТО СДЕЛАТЬ ===")
        for index, hint in enumerate(hints, start=1):
            print(f"{index}. {hint}\n")
    else:
        print("=== ЧТО СДЕЛАТЬ ===")
        print("1. Критичных проблем не найдено — можно продолжать работу.\n")


async def main() -> None:
    print("=== СИСТЕМНАЯ ИНФОРМАЦИЯ ===")
    print(check_system_info())

    env_file_values = dotenv_values()

    required = [
        "TELEGRAM_BOT_TOKEN",
        "DB_DSN",
        "WEBHOOK_URL",
        "DOMAIN",
    ]

    collected_results: List[CheckResult] = []

    env_results = check_env_vars(required, env_file_values)
    for result in env_results:
        result.display()
        collected_results.append(result)

    db_dsn = os.getenv("DB_DSN")
    dns_hosts, tcp_targets, dsn_info = prepare_network_targets(db_dsn)

    print("=== СЕТЬ ===")
    dns_results = check_dns(dns_hosts)
    for result in dns_results:
        result.display()
        collected_results.append(result)

    for host, port in tcp_targets:
        tcp_result = check_tcp_connectivity(host, port)
        tcp_result.display()
        collected_results.append(tcp_result)

    print("=== ВНЕШНИЕ СЕРВИСЫ ===")
    telegram_result = await check_telegram(os.getenv("TELEGRAM_BOT_TOKEN"))
    telegram_result.display()
    collected_results.append(telegram_result)

    db_result = await check_database(db_dsn, dsn_info)
    db_result.display()
    collected_results.append(db_result)

    print("=== ЛОКАЛЬНЫЕ ПОРТЫ ===")
    ports_result = check_listening_ports()
    ports_result.display()
    collected_results.append(ports_result)

    file_dsn_value = env_file_values.get("DB_DSN")
    file_dsn_info = parse_db_dsn(file_dsn_value) if file_dsn_value else None

    print_recommendations(collected_results, dsn_info, file_dsn_info)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Прервано пользователем")
