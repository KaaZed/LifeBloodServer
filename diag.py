import asyncio
import os
import subprocess

import httpx
import psutil
from dotenv import load_dotenv
from psutil import AccessDenied, NoSuchProcess, ZombieProcess

load_dotenv()


async def main() -> None:
    print("TOKEN:", os.getenv("TELEGRAM_BOT_TOKEN"))
    print("DB_DSN:", os.getenv("DB_DSN"))
    try:
        async with httpx.AsyncClient(timeout=10) as cli:
            resp = await cli.get(
                f"https://api.telegram.org/bot{os.getenv('TELEGRAM_BOT_TOKEN')}/getMe"
            )
            print("getMe:", resp.text)
    except Exception as exc:
        print("getMe error:", exc)

    print("-- ss -tulpen --")
    try:
        print(subprocess.check_output(["ss", "-tulpen"], text=True))
    except FileNotFoundError:
        print("ss not found: установите пакет iproute2 и повторите проверку.")
    except subprocess.CalledProcessError as exc:
        print(f"ss завершился с кодом {exc.returncode}: {exc}")

    print("-- psutil listening sockets --")
    try:
        for conn in psutil.net_connections(kind="inet"):
            if conn.status != psutil.CONN_LISTEN:
                continue
            try:
                proc_name = psutil.Process(conn.pid).name() if conn.pid else "?"
            except (NoSuchProcess, AccessDenied, ZombieProcess):
                proc_name = "?"
            laddr = getattr(conn.laddr, "ip", conn.laddr[0])
            port = getattr(conn.laddr, "port", conn.laddr[1])
            print(f"{laddr}:{port} -> PID {conn.pid} {proc_name}")
    except AccessDenied:
        print("Недостаточно прав для просмотра сокетов, запустите с sudo.")
    except Exception as exc:
        print("psutil.net_connections error:", exc)


if __name__ == "__main__":
    asyncio.run(main())
