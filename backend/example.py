import asyncio
import json
import logging
import random
from typing import Any

import twitchio
from twitchio import authentication, eventsub
from twitchio.ext import commands
import os
from dotenv import load_dotenv
from pathlib import Path
from loguru import logger
import httpx
import sys

# Load environment variables from .env files (root and backend) for flexibility
load_dotenv()
load_dotenv("backend/.env")

# NOTE: These environment variables should be defined in your .env file
# according to the .env.example format
CLIENT_ID = os.getenv("TWITCH_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET", "")
BOT_ID = os.getenv("TWITCH_BOT_ID", "")
OWNER_ID = os.getenv("TWITCH_OWNER_ID", "")
CHANNEL_LOGIN = (os.getenv("TWITCH_CHANNEL") or "bootoshicodes").strip()

def configure_logging() -> None:
    """Configure Loguru as the sole logger with colored tags.

    - Suppresses stdlib logging from TwitchIO to reduce duplicate log lines
    - Adds a single colorized sink to stdout
    """
    logger.remove()
    logger.add(
        sys.stdout,
        colorize=True,
        # Color style inspired by Loguru best practices
        # Ref: Better Stack Loguru guide
        format="<green>{time:HH:mm:ss.SSS}</green> | <level>{level: <7}</level> | <cyan>{name}</cyan> | <level>{message}</level>",
        backtrace=False,
        diagnose=False,
    )
    # Quiet most stdlib logs from dependencies
    logging.getLogger("twitchio").setLevel(logging.WARNING)
    logging.getLogger("twitchio.eventsub").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)


class Bot(commands.Bot):
    def __init__(self, **kwargs: Any) -> None:
        """Custom TwitchIO Bot with EventSub chat tracking and send helpers.

        Notes:
        - Uses a locally saved user token (backend/.twitch_user_token.json) to
          authorize chat send capability (scope: chat:edit).
        - Subscribes to ChatMessage events for the configured channel
          (`CHANNEL_LOGIN`), enabling message tracking without legacy IRC.
        - Provides a programmatic send helper using PartialUser API.
        """
        super().__init__(**kwargs)
        self.target_channel_login: str = CHANNEL_LOGIN
        self._broadcaster_id: str | None = None
        self._target_partial_user = None  # cache PartialUser for send

    async def setup_hook(self) -> None:
        # Commands component intentionally not added; we respond based on keywords only

        # 1) Try to add a locally saved user token so we can send chat.
        #    File is produced by backend/generate_user_token.py
        token_path = Path("backend/.twitch_user_token.json")
        if token_path.exists():
            try:
                data = json.loads(token_path.read_text() or "{}")
                access = (data.get("access_token") or "").strip()
                refresh = (data.get("refresh_token") or "").strip()
                if access and refresh:
                    await self.add_token(access, refresh)
                    logger.info("Loaded user token from backend/.twitch_user_token.json for chat send capability")
                else:
                    logger.warning("backend/.twitch_user_token.json missing access/refresh; skipping add_token")
            except Exception as exc:
                logger.warning(f"Failed to load user token file: {exc}")
        else:
            logger.warning("No backend/.twitch_user_token.json found; chat sending may be unavailable")

        # 2) Determine broadcaster id for the target channel using Helix
        try:
            self._broadcaster_id = await self._fetch_user_id_by_login(self.target_channel_login)
            logger.info(f"Resolved broadcaster id for {self.target_channel_login}: {self._broadcaster_id}")
        except Exception as exc:
            logger.warning(f"Failed to resolve broadcaster id for {self.target_channel_login}: {exc}")

        # 3) Subscribe to chat messages via EventSub for the target broadcaster
        try:
            if self._broadcaster_id:
                chat = eventsub.ChatMessageSubscription(
                    broadcaster_user_id=self._broadcaster_id,
                    user_id=BOT_ID,
                )
                # Prefer websocket EventSub for continuity
                await self.subscribe_websocket(chat)
                logger.info("Subscribed to ChatMessageSubscription via websocket for target channel")
        except Exception as exc:
            logger.warning(f"Chat EventSub subscription failed: {exc}")

        # 4) Back-compat: if pre-existing TwitchIO token store exists, subscribe for each
        try:
            tio_tokens = Path(".tio.tokens.json")
            if tio_tokens.exists():
                tokens = json.loads(tio_tokens.read_text() or "{}")
                for user_id in tokens:
                    if str(user_id) == str(BOT_ID):
                        continue
                    try:
                        chat = eventsub.ChatMessageSubscription(broadcaster_user_id=user_id, user_id=BOT_ID)
                        await self.subscribe_websocket(chat)
                        logger.debug(f"Subscribed to chat for stored user_id={user_id}")
                    except Exception as exc:
                        logger.warning(f"Failed to subscribe for stored user_id={user_id}: {exc}")
        except Exception as exc:
            logger.debug(f"No .tio.tokens.json processing performed: {exc}")

    async def event_ready(self) -> None:
        logger.success(f"<bold><yellow>[READY]</yellow></bold> Logged in as: {self.user}")
        # Proactively send a greeting to the target channel if we can
        try:
            if self._broadcaster_id:
                await self._send_message_to_broadcaster(self._broadcaster_id, "Bot online. Keyword responder active.")
        except Exception as exc:
            logger.debug(f"Greeting send skipped/failed: {exc}")

    async def event_oauth_authorized(self, payload: authentication.UserTokenPayload) -> None:
        # Stores tokens in .tio.tokens.json by default; can be overriden to use a DB for example
        # Adds the token to our Client to make requests and subscribe to EventSub...
        await self.add_token(payload.access_token, payload.refresh_token)

        if payload.user_id == BOT_ID:
            return

        # Subscribe to chat for new authorizations...
        chat = eventsub.ChatMessageSubscription(broadcaster_user_id=payload.user_id, user_id=BOT_ID)
        await self.subscribe_websocket(chat)

    async def event_message(self, payload: twitchio.ChatMessage) -> None:
        """Track and log every chat message in the subscribed channel(s).

        References:
        - Event: event_message(payload: twitchio.ChatMessage)
          Requires ChatMessageSubscription per broadcaster
          Docs: https://twitchio.dev/en/latest/ (events reference)
        """
        try:
            chan = getattr(getattr(payload, "broadcaster", None), "name", "?")
            user = getattr(getattr(payload, "chatter", None), "name", "?")
            text = getattr(payload, "text", "")

            # Ignore the bot's own messages (by name and id) BEFORE logging chats
            try:
                bot_name = (getattr(self.user, "name", "") or "").lower()
                if user and bot_name and user.lower() == bot_name:
                    return
                bot_id_str = str(getattr(self, "bot_id", "") or "")
                author_id = str(getattr(getattr(payload, "chatter", None), "id", "") or "")
                if bot_id_str and author_id and bot_id_str == author_id:
                    return
            except Exception:
                pass

            # Log the chat line (excluding the bot itself)
            logger.info(f"<cyan>[CHAT]</cyan> [{chan}] <{user}> {text}")

            # Keyword-based replies (case-insensitive)
            text_l = (text or "").lower()
            reply: str | None = None
            matched: str | None = None
            if "chicken" in text_l:
                reply = "IM NOT A CHICKEN!"
                matched = "chicken"
            elif "questboo" in text_l or "duck" in text_l:
                reply = "hi"
                matched = "questboo" if "questboo" in text_l else "duck"

            if reply and self._broadcaster_id:
                # Log the keyword hit
                logger.info(f"<magenta>[HIT]</magenta> @{user} in #{chan}: found '{matched}' -> reply '{reply}'")
                await self._send_message_to_broadcaster(self._broadcaster_id, reply)
        except Exception as exc:
            logger.debug(f"Failed to log chat message: {exc}")

    async def event_command_error(self, ctx: commands.Context, error: Exception) -> None:
        """Verbose command error logging for easier diagnosis."""
        try:
            logger.error(f"Command error in '{getattr(ctx, 'command', None)}': {error}")
        except Exception:
            logger.error(f"Command error: {error}")

    async def _fetch_user_id_by_login(self, login: str) -> str:
        """Resolve a user's numeric id from their login using Helix.

        Requires `TWITCH_CLIENT_ID` and a valid user token (already added via
        add_token) to authorize the Helix call.
        """
        client_id = (CLIENT_ID or "").strip()
        if not client_id:
            raise RuntimeError("Missing TWITCH_CLIENT_ID for Helix user lookup")
        # Grab any available access token from the internal token store via env
        # Our token was added via add_token earlier; we reuse the same bearer here
        # by reading from the local file for simplicity.
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

    async def _send_message_to_broadcaster(self, broadcaster_id: str, message: str) -> None:
        """Send a message into the broadcaster's chat using PartialUser API.

        Requires chat:edit scope on the added user token.
        Docs example: PartialUser.send_message(sender=bot.user, message="...")
        """
        try:
            if self._target_partial_user is None:
                self._target_partial_user = self.create_partialuser(broadcaster_id)
            await self._target_partial_user.send_message(sender=self.user, message=message)
            logger.success(f"<green>[SEND]</green> -> #{self.target_channel_login}: '{message}'")
        except Exception as exc:
            logger.warning(f"Failed to send message to broadcaster_id={broadcaster_id}: {exc}")


class GeneralCommands(commands.Component):
    """Placeholder component retained for structure; commands are disabled.

    We intentionally do not register or use command handlers in this example,
    per the requirement to reply only by reading chat messages and keyword
    detection. Keeping the class avoids broader refactors.
    """
    pass


def main() -> None:
    # Use Loguru-only logging with colors
    configure_logging()

    async def runner() -> None:
        async with Bot(
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            bot_id=BOT_ID,
            owner_id=OWNER_ID,
            prefix="!",
        ) as bot:
            await bot.start()

    try:
        asyncio.run(runner())
    except KeyboardInterrupt:
        logger.warning("Shutting down due to KeyboardInterrupt")


if __name__ == "__main__":
    main()