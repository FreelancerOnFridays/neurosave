"""Hot-reload dev runner. Usage: uv run python dev.py"""
from __future__ import annotations

import asyncio
import subprocess
import sys
from watchfiles import awatch


_WATCH = ["bot", "services", "workers", "db", "main.py", "config.py"]


def _only_py(change: object, path: str) -> bool:
    return path.endswith(".py")


async def main() -> None:
    proc: subprocess.Popen[bytes] | None = None

    def restart() -> None:
        nonlocal proc
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        proc = subprocess.Popen([sys.executable, "main.py"])

    print("🚀 Starting bot…")
    restart()

    async for _ in awatch(*_WATCH, watch_filter=_only_py):
        print("\n🔄 Change detected — restarting…\n")
        restart()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Dev server stopped.")
