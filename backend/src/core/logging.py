"""Centralized Loguru logging setup.

Why: Keep logging configuration consistent across modules and allow structured
logging with levels. Use this at app startup before importing modules that log.
"""

from __future__ import annotations

from loguru import logger
import os
import sys


def setup_logging() -> None:
    """Configure Loguru sinks and levels.

    - Logs to stderr with a concise format suitable for dev.
    - Respects `LOG_LEVEL` env var (default: INFO).
    - Avoid duplicate handlers if called multiple times.
    """
    # Remove any previously configured handlers to avoid duplicates.
    logger.remove()

    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    # Register custom semantic levels for colored categories
    def _ensure_level(name: str, no: int, color: str) -> None:
        try:
            logger.level(name)
        except Exception:
            logger.level(name, no=no, color=color)

    _ensure_level("CHAT", no=21, color="<cyan>")
    _ensure_level("HIT", no=22, color="<magenta>")
    _ensure_level("PIPE", no=23, color="<magenta>")
    _ensure_level("VOICE", no=24, color="<yellow>")
    _ensure_level("QUEUE", no=26, color="<blue>")
    _ensure_level("TURN", no=27, color="<blue>")

    # Human-friendly, timestamped single-line format
    logger.add(
        sys.stderr,
        level=log_level,
        backtrace=False,
        diagnose=False,
        # Color timestamp, level, and message using level's default color
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        colorize=True,
    )
