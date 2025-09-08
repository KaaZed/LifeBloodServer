import os, asyncio, subprocess, httpx
from dotenv import load_dotenv

load_dotenv()


async def main():
    print("TOKEN:", os.getenv("TELEGRAM_BOT_TOKEN"))
    print("DB_DSN:", os.getenv("DB_DSN"))
    try:
        async with httpx.AsyncClient(timeout=10) as cli:
            r = await cli.get(f"https://api.telegram.org/bot{os.getenv('TELEGRAM_BOT_TOKEN')}/getMe")
            print("getMe:", r.text)
    except Exception as e:
        print("getMe error:", e)
    print(subprocess.check_output(['ss', '-tulpen']).decode())


if __name__ == "__main__":
    asyncio.run(main())
    import psutil
    for c in psutil.net_connections(kind="inet"):
        if c.status == psutil.CONN_LISTEN:
            proc = psutil.Process(c.pid).name() if c.pid else "?"
            print(f"{c.laddr.ip}:{c.laddr.port} -> PID {c.pid} {proc}")