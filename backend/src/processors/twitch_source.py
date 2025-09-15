"""TwitchChatSource: custom FrameProcessor that ingests chat lines.

Emits canonical TextFrame messages for Twitch chat into the pipeline without
blocking mic input. Designed to be placed in a parallel branch and normalized
via Producer/Consumer into the common conversation tail.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Callable, Optional

from loguru import logger

from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.frames.frames import (
    StartFrame,
    EndFrame,
    CancelFrame,
    StopFrame,
    TextFrame,
)


@dataclass
class ChatItem:
    user: str
    text: str


class TwitchChatSource(FrameProcessor):
    """Ingress for Twitch messages. Non-blocking and branch-local.

    - External code calls `ingest(user, text)` to enqueue chat.
    - On each `process_frame` tick, drain at most a few items (no blocking).
    - Optional soft backpressure: if LLM/TTS busy, pause draining.
    - Emits canonical TextFrame: "Twitch Chat User [<user>] says [<text>]".
    """

    def __init__(self, cooldown_secs: float = 0.0, should_emit: Optional[Callable[[], bool]] = None) -> None:
        super().__init__()
        self._queue: asyncio.Queue[ChatItem] = asyncio.Queue()
        self._cooldown = float(cooldown_secs)
        self._should_emit = should_emit
        self._last_emit = 0.0
        self._started = asyncio.Event()
        self._stopping = asyncio.Event()
        self._drain_task: asyncio.Task | None = None

    async def ingest(self, user: str, text: str) -> None:
        user = (user or "").strip()
        text = (text or "").strip()
        if not user or not text:
            return
        await self._queue.put(ChatItem(user=user, text=text))

    async def process_frame(self, frame, direction: FrameDirection):
        # Always allow base class lifecycle handling
        await super().process_frame(frame, direction)

        # Start/stop lifecycle to manage background drain loop
        if isinstance(frame, StartFrame):
            if not self._started.is_set():
                self._started.set()
                if self._drain_task is None:
                    self._drain_task = asyncio.create_task(self._drain_loop())
        elif isinstance(frame, (EndFrame, CancelFrame, StopFrame)):
            self._stopping.set()

        # Forward the original frame
        await self.push_frame(frame, direction)

    async def _drain_loop(self) -> None:
        # Wait until the processor has fully started
        await self._started.wait()
        while not self._stopping.is_set():
            try:
                item = await asyncio.wait_for(self._queue.get(), timeout=0.25)
            except asyncio.TimeoutError:
                continue
            # Optional backpressure: hold while not permitted to emit
            if self._should_emit and not self._should_emit():
                await asyncio.sleep(0.1)
                await self._queue.put(item)
                continue
            now = time.monotonic()
            if self._cooldown and (now - self._last_emit) < self._cooldown:
                # Simple cooldown: requeue and wait a bit
                await asyncio.sleep(self._cooldown)
            text = f"Twitch Chat User [{item.user}] says [{item.text}]"
            logger.log("PIPE", f"[PIPE<-TWITCH] {text}")
            await self.push_frame(TextFrame(text=text), FrameDirection.DOWNSTREAM)
            self._last_emit = time.monotonic()
