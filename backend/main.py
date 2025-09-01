"""Minimal starter that delegates to the modular src runner."""

from __future__ import annotations

import asyncio

from src.pipeline.runner import AppRunner
from src.core.logging import setup_logging


async def _main():
    setup_logging()
    app = AppRunner()
    await app.run()


if __name__ == "__main__":
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        pass