"""Twitch chat → Pipecat pipeline integration.

This plugin turns the standalone example.py Twitch logic into a reusable
integration that:

- Subscribes to Twitch chat via EventSub (TwitchIO v3).
- Detects trigger keywords (questboo/duck/chicken by default).
- Enqueues requests and serializes turns to avoid rate limits.
- Injects programmatic text into the running PipelineTask so the LLM+TTS path
  runs without mic input.
- Optionally echoes the assistant's final text back into chat (one message per
  turn) while still speaking via TTS.

The injected user message uses the exact format requested for chat history:

    "Twitch Chat User [USERNAME] says [WHAT THEY SAID IN CHAT]"

This text is pushed as a TextFrame at the pipeline input so it flows through
the context aggregator's user() stage, preserving continuous chat history with
voice turns.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Optional
from collections import deque

from loguru import logger
import httpx

import twitchio
from twitchio import authentication, eventsub
from twitchio.ext import commands

from pipecat.frames.frames import (
    TextFrame,
    LLMFullResponseStartFrame,
    LLMFullResponseEndFrame,
)
from pipecat.pipeline.task import PipelineTask

from ..core.state import SharedState
from ..config.settings import Settings
from .base import BaseIntegration


# No queued worker; TwitchChatSource handles queuing/backpressure.


class TwitchChatIntegration(BaseIntegration):
    """Listens to Twitch chat, queues triggers, and injects text into pipeline."""

    def __init__(self, settings: Settings, state: SharedState, source) -> None:
        self.settings = settings
        self.state = state
        self.task: Optional[PipelineTask] = None
        self.source = source  # TwitchChatSource

        # Config from env (same as example.py expectations)
        self.channel_login = (os.getenv("TWITCH_CHANNEL") or "bootoshicodes").strip()
        # Comma-separated keyword list; defaults align with example.py
        self._keywords = {
            s.strip().lower()
            for s in (os.getenv("TWITCH_TRIGGER_WORDS", "questboo,duck,chicken").split(","))
            if s.strip()
        }
        # Cooldown between dequeued turns to minimize chat spam
        try:
            self._cooldown_secs = float(os.getenv("TWITCH_ACTIVATION_COOLDOWN_SECS", "3"))
        except Exception:
            self._cooldown_secs = 3.0
        self._echo_to_chat = (os.getenv("TWITCH_ECHO_ASSISTANT_TO_CHAT", "1").strip() != "0")

        # Runtime state
        self._current_user: Optional[str] = None
        self._pending_users = deque()
        self._collecting_llm = False
        self._llm_buf: list[str] = []

        # Twitch client
        self._bot: Optional[_Bot] = None

    async def on_pipeline_ready(self, task: PipelineTask) -> None:
        """Called once pipeline is created. Registers taps and starts bot/worker."""
        self.task = task

        # Tap downstream frames to know when a turn starts/ends and to collect
        # the assistant's final text for optional chat echo. Also detect when a
        # Twitch-originated user text enters the common tail so we can attribute
        # the next LLM turn to that user for chat echoing.
        @task.event_handler("on_frame_reached_downstream")
        async def _capture(_, frame):  # noqa: D401
            if isinstance(frame, LLMFullResponseStartFrame):
                self._collecting_llm = True
                self._llm_buf.clear()
                # Attribute next LLM turn to first pending twitch user
                if not self._current_user and self._pending_users:
                    try:
                        self._current_user = self._pending_users.popleft()
                    except Exception:
                        self._current_user = None
            elif isinstance(frame, LLMFullResponseEndFrame):
                # LLM finished; optionally echo the final composed text to chat
                self._collecting_llm = False
                final = "".join(self._llm_buf).strip()
                if final and self._echo_to_chat and self._current_user and self._bot:
                    try:
                        await self._bot.send_message_to_broadcaster(
                            self._bot.broadcaster_id,
                            f"@{self._current_user} {final[:350]}",
                        )
                    except Exception as exc:
                        logger.warning(f"Twitch echo failed: {exc}")
                    finally:
                        # Clear attribution after echoing
                        self._current_user = None
            elif self._collecting_llm and hasattr(frame, "text"):
                try:
                    txt = str(getattr(frame, "text", "") or "")
                    if txt:
                        self._llm_buf.append(txt)
                except Exception:
                    pass

        # Start the twitch bot
        asyncio.create_task(self._run_bot())

    async def _run_bot(self) -> None:
        """Start the TwitchIO bot in a managed context."""
        self._bot = _Bot(
            integration=self,
            client_id=os.getenv("TWITCH_CLIENT_ID", ""),
            client_secret=os.getenv("TWITCH_CLIENT_SECRET", ""),
            bot_id=os.getenv("TWITCH_BOT_ID", ""),
            owner_id=os.getenv("TWITCH_OWNER_ID", ""),
            prefix="!",
        )
        async with self._bot as bot:
            await bot.start()

    async def on_keyword_hit(self, user: str, text: str) -> None:
        """Send a chat message into the TwitchChatSource (non-blocking)."""
        try:
            self._pending_users.append(user)
            await self.source.ingest(user, text)
        except Exception as exc:
            logger.warning(f"Failed to ingest twitch chat into pipeline: {exc}")


class _Bot(commands.Bot):
    """Slim wrapper over TwitchIO to detect keywords and enable sending chat."""

    def __init__(self, integration: TwitchChatIntegration, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.integration = integration
        self.channel_login = integration.channel_login
        self.broadcaster_id: Optional[str] = None
        self._target_partial_user = None

    async def setup_hook(self) -> None:
        # Load user token for chat send capability (same file as example.py)
        token_path = Path("backend/.twitch_user_token.json")
        if token_path.exists():
            try:
                data = json.loads(token_path.read_text() or "{}")
                access = (data.get("access_token") or "").strip()
                refresh = (data.get("refresh_token") or "").strip()
                if access and refresh:
                    await self.add_token(access, refresh)
                    logger.info(
                        "Loaded user token from backend/.twitch_user_token.json for chat send capability"
                    )
                else:
                    logger.warning(
                        "backend/.twitch_user_token.json missing access/refresh; skipping add_token"
                    )
            except Exception as exc:
                logger.warning(f"Failed to load user token file: {exc}")
        else:
            logger.warning(
                "No backend/.twitch_user_token.json found; chat sending may be unavailable"
            )

        # Resolve broadcaster id for configured channel
        try:
            self.broadcaster_id = await self._fetch_user_id_by_login(self.channel_login)
            logger.info(
                f"Resolved broadcaster id for {self.channel_login}: {self.broadcaster_id}"
            )
        except Exception as exc:
            logger.warning(f"Failed to resolve broadcaster id: {exc}")

        # Subscribe to chat messages via EventSub
        try:
            if self.broadcaster_id:
                chat = eventsub.ChatMessageSubscription(
                    broadcaster_user_id=self.broadcaster_id,
                    user_id=os.getenv("TWITCH_BOT_ID", ""),
                )
                await self.subscribe_websocket(chat)
                logger.info("Subscribed to ChatMessageSubscription via websocket for target channel")
        except Exception as exc:
            logger.warning(f"Chat EventSub subscription failed: {exc}")

        # Back-compat for any pre-stored tokens in .tio.tokens.json (optional)
        try:
            tio_tokens = Path(".tio.tokens.json")
            if tio_tokens.exists():
                tokens = json.loads(tio_tokens.read_text() or "{}")
                for user_id in tokens:
                    if str(user_id) == str(os.getenv("TWITCH_BOT_ID", "")):
                        continue
                    try:
                        chat = eventsub.ChatMessageSubscription(
                            broadcaster_user_id=user_id,
                            user_id=os.getenv("TWITCH_BOT_ID", ""),
                        )
                        await self.subscribe_websocket(chat)
                        logger.debug(
                            f"Subscribed to chat for stored user_id={user_id}"
                        )
                    except Exception as exc:
                        logger.warning(
                            f"Failed to subscribe for stored user_id={user_id}: {exc}"
                        )
        except Exception as exc:
            logger.debug(f"No .tio.tokens.json processing performed: {exc}")

    async def event_ready(self) -> None:
        logger.success(
            f"<bold><yellow>[READY]</yellow></bold> Twitch bot logged in as: {self.user}"
        )
        # Optional greeting, like example.py
        try:
            if self.broadcaster_id:
                await self.send_message_to_broadcaster(
                    self.broadcaster_id, "Bot online. Keyword responder active."
                )
        except Exception as exc:
            logger.debug(f"Greeting send skipped/failed: {exc}")

    async def event_oauth_authorized(self, payload: authentication.UserTokenPayload) -> None:
        await self.add_token(payload.access_token, payload.refresh_token)
        if payload.user_id == os.getenv("TWITCH_BOT_ID", ""):
            return
        chat = eventsub.ChatMessageSubscription(
            broadcaster_user_id=payload.user_id, user_id=os.getenv("TWITCH_BOT_ID", "")
        )
        await self.subscribe_websocket(chat)

    async def event_message(self, payload: twitchio.ChatMessage) -> None:
        """Detect keywords and enqueue a turn (ignore own messages)."""
        try:
            user = getattr(getattr(payload, "chatter", None), "name", "")
            text = getattr(payload, "text", "") or ""

            # ignore our own messages by name/id
            try:
                bot_name = (getattr(self.user, "name", "") or "").lower()
                if user and bot_name and user.lower() == bot_name:
                    return
                bot_id_str = str(os.getenv("TWITCH_BOT_ID", "") or "")
                author_id = str(getattr(getattr(payload, "chatter", None), "id", "") or "")
                if bot_id_str and author_id and bot_id_str == author_id:
                    return
            except Exception:
                pass

            # Log the chat line (excluding the bot itself)
            chan = getattr(getattr(payload, "broadcaster", None), "name", "?")
            logger.info(f"<cyan>[CHAT]</cyan> [{chan}] <{user}> {text}")

            # Keyword detection (contains-any, case-insensitive)
            text_l = text.lower()
            if any(k in text_l for k in self.integration._keywords):
                logger.info(
                    f"<magenta>[HIT]</magenta> @{user} in #{chan}: trigger detected → queued"
                )
                await self.integration.on_keyword_hit(user=user, text=text)
        except Exception as exc:
            logger.debug(f"event_message error: {exc}")

    async def send_message_to_broadcaster(self, broadcaster_id: Optional[str], message: str) -> None:
        if not broadcaster_id:
            return
        try:
            if self._target_partial_user is None:
                self._target_partial_user = self.create_partialuser(broadcaster_id)
            await self._target_partial_user.send_message(sender=self.user, message=message)
            logger.success(
                f"<green>[SEND]</green> -> #{self.channel_login}: '{message}'"
            )
        except Exception as exc:
            logger.warning(
                f"Failed to send message to broadcaster_id={broadcaster_id}: {exc}"
            )

    async def _fetch_user_id_by_login(self, login: str) -> str:
        client_id = (os.getenv("TWITCH_CLIENT_ID") or "").strip()
        if not client_id:
            raise RuntimeError("Missing TWITCH_CLIENT_ID for Helix user lookup")
        token_path = Path("backend/.twitch_user_token.json")
        access = None
        try:
            if token_path.exists():
                data = json.loads(token_path.read_text() or "{}")
                access = (data.get("access_token") or "").strip()
        except Exception:
            access = None
        if not access:
            raise RuntimeError("No access token available to query Helix /users")

        url = "https://api.twitch.tv/helix/users"
        headers = {"Client-ID": client_id, "Authorization": f"Bearer {access}"}
        params = {"login": login}
        with httpx.Client(timeout=10.0) as client:
            r = client.get(url, headers=headers, params=params)
            r.raise_for_status()
            data = r.json()
            arr = data.get("data") or []
            if not arr:
                raise RuntimeError(f"No Helix user data returned for login '{login}'")
            return str(arr[0].get("id"))
