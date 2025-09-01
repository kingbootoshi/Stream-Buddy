"""
Standalone Twitch chat runner for local testing.

Run this file by itself to verify that:
- We can connect to Twitch IRC over WebSocket
- We can read chat messages in real-time
- We detect @questboo mentions (case/space-insensitive)
- We keep a small ring buffer of recent chat lines

Usage:
  1) Copy `.env.example` to `.env` and fill in:
     - TWITCH_CHANNEL (e.g., yourchannel)
     - TWITCH_BOT_USERNAME (e.g., questboobot)
     - TWITCH_OAUTH_TOKEN (format: oauth:xxxxxxxx; must include chat:read scope)
  2) pip install -r backend/requirements.txt
  3) python3 backend/twitch_chat_runner.py

This does NOT interact with the Pipecat pipeline. It is purely for smoke testing
Twitch chat ingestion before wiring into the main backend.
"""

from __future__ import annotations

import asyncio
import os
import re
import time
from collections import deque
from typing import Deque, Dict, List

try:
    from dotenv import load_dotenv

    # Load both root .env and backend/.env if present. Later calls won't
    # override already-set variables, so order is safe.
    load_dotenv(".env")
    load_dotenv("backend/.env")
except Exception:
    # It's okay if python-dotenv is not installed; env vars can come from shell
    pass

from loguru import logger
from twitchio.ext import commands


# Regex to match mentions like "@questboo" or "@quest boo" (case-insensitive)
MENTION = re.compile(r"@quest\s*boo\b", re.IGNORECASE)


class TwitchChatRunner(commands.Bot):
    """Minimal Twitch chat client with ring buffer and mention detection.

    This class connects to Twitch IRC using twitchio, appends each incoming
    message to an in-memory ring buffer, and logs when an @questboo mention
    is detected. A simple cooldown prevents rapid re-triggers.
    """

    def __init__(self, chat_ring: Deque[Dict], cooldown_seconds: float) -> None:
        # Required environment variables
        token = os.environ.get("TWITCH_OAUTH_TOKEN", "").strip()
        channel = os.environ.get("TWITCH_CHANNEL", "").strip()

        if not token or not channel:
            raise RuntimeError(
                "Missing TWITCH_OAUTH_TOKEN or TWITCH_CHANNEL. Check your .env."
            )

        # Initialize twitchio bot
        super().__init__(token=token, initial_channels=[channel], prefix="!")

        self.chat_ring = chat_ring
        self.cooldown_seconds = cooldown_seconds
        self._last_activation_at = 0.0

        # Cosmetic: show which account we intend to use (optional)
        bot_user = os.environ.get("TWITCH_BOT_USERNAME", "(unknown)")
        logger.info(
            f"Preparing Twitch chat runner as '{bot_user}' for channel '#{channel}'"
        )

    async def event_ready(self):  # noqa: D401
        """Called when the bot has connected and joined the channel."""
        logger.info(f"[twitch] ready as {self.nick}; joined #{self.initial_channels[0]}")

    async def event_message(self, message):  # noqa: D401
        """Handle incoming chat messages and detect @questboo mentions."""
        # Avoid echo (messages the bot sent itself)
        if getattr(message, "echo", False):
            return

        author = message.author.name if message.author else "unknown"
        text = message.content or ""
        ts_ms = int(time.time() * 1000)

        # Append to ring buffer
        self.chat_ring.append({"user": author, "text": text, "ts": ts_ms})

        logger.info(f"{author}: {text}")

        # Detect @questboo (robust to spaces and case)
        if MENTION.search(text):
            now = time.time()
            if now - self._last_activation_at < self.cooldown_seconds:
                logger.debug("mention ignored due to cooldown")
                return
            self._last_activation_at = now

            # Take the last 20 lines for context (if present)
            recent20: List[Dict] = list(self.chat_ring)[-20:]
            logger.success(
                "@questboo mention detected — would trigger activation with last 20 messages"
            )
            # Pretty log the snapshot
            for m in recent20:
                logger.debug(f"ctx> {m['user']}: {m['text']}")


async def main() -> None:
    """Entrypoint to run the Twitch chat runner until interrupted."""
    # Keep a modest backlog; we only need 20 for context, but 500 provides cushion
    chat_ring: Deque[Dict] = deque(maxlen=500)
    cooldown = float(os.getenv("TWITCH_ACTIVATION_COOLDOWN_SECS", "3"))

    bot = TwitchChatRunner(chat_ring, cooldown)
    await bot.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass


