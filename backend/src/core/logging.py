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

    # Human-friendly, timestamped single-line format
    logger.add(
        sys.stderr,
        level=log_level,
        backtrace=False,
        diagnose=False,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {message}",
    )


