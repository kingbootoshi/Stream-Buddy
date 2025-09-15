"""TurnArbiter: serialize voice and Twitch turns with voice priority.

This processor intercepts LLMMessagesAppendFrame from both branches and queues
them so only one LLM turn can run at a time. It gives voice priority, but
ensures chat does not starve (fairness). It also publishes per-turn metadata
into SharedState so integrations can deterministically echo assistant replies
back into Twitch chat only for chat-originated turns.

Notes:
- We do not rely on seeing downstream TTS frames here (this processor sits
  before LLM/TTS). Instead, we listen to SharedState events: handlers flip
  `tts_speaking` when TTS starts/stops, and we release the turn lock when TTS
  stops. A watchdog timer provides a fallback if providers misbehave.
"""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass
from typing import Literal, Optional

from loguru import logger

from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.frames.frames import Frame, LLMMessagesAppendFrame

from ..core.state import SharedState


Origin = Literal["voice", "twitch", "unknown"]


@dataclass
class _QueuedTurn:
    frame: LLMMessagesAppendFrame
    origin: Origin
    user: Optional[str]
    raw: str


class TurnArbiter(FrameProcessor):
    """Serialize LLMMessagesAppendFrame turns and publish turn metadata.

    - Voice priority (no preemption of an active turn).
    - Fairness: after N voice turns, allow one twitch turn if queued.
    - Busy window: from release until TTS stops (via SharedState listener).
    - Watchdog timeout to avoid deadlocks.
    """

    def __init__(
        self,
        state: SharedState,
        fairness_after_voice: int = 1,
        turn_timeout_secs: float = 60.0,
    ) -> None:
        super().__init__()
        self.state = state
        self._voice_q: deque[_QueuedTurn] = deque()
        self._twitch_q: deque[_QueuedTurn] = deque()
        self._current: Optional[_QueuedTurn] = None
        self._busy = False
        self._voices_since_last_twitch = 0
        self._fairness_after_voice = max(0, int(fairness_after_voice))
        self._timeout_secs = float(turn_timeout_secs)
        self._timeout_task: Optional[asyncio.Task] = None

        # Subscribe to SharedState to learn when TTS stops
        self.state.add_listener(self._on_state_event)

    # --- SharedState listener -------------------------------------------------
    def _on_state_event(self, event: str, value) -> None:  # noqa: ANN001 - generic
        if event == "tts_speaking_changed":
            try:
                speaking = bool(value)
            except Exception:
                speaking = False
            if not speaking:
                # When TTS stops, the current turn is over.
                if self._current is not None:
                    asyncio.get_event_loop().create_task(self._finish_current_turn())

    # --- Core queueing -------------------------------------------------------
    async def process_frame(self, frame: Frame, direction: FrameDirection):
        # Always allow base class lifecycle hooks
        await super().process_frame(frame, direction)

        # Queue all user appends; do not let run_llm=True leak through directly
        if direction == FrameDirection.DOWNSTREAM and isinstance(frame, LLMMessagesAppendFrame):
            origin, user, raw = self._classify(frame)

            # Coerce run_llm to False until we release this turn
            try:
                frame.run_llm = False
            except Exception:
                pass

            item = _QueuedTurn(frame=frame, origin=origin, user=user, raw=raw)
            if origin == "voice":
                self._voice_q.append(item)
            elif origin == "twitch":
                self._twitch_q.append(item)
            else:
                # Unknown goes to twitch queue to avoid starving chat
                self._twitch_q.append(item)

            logger.log(
                "QUEUE",
                f"add origin={origin} user={user} sizes v={len(self._voice_q)} t={len(self._twitch_q)}",
            )

            # Try to release immediately if idle
            await self._release_next_if_idle()
            return  # swallow the append (we will re-emit when it’s this turn)

        # Pass through all other frames unmodified
        await self.push_frame(frame, direction)

    def _classify(self, f: LLMMessagesAppendFrame) -> tuple[Origin, Optional[str], str]:
        origin: Origin = "unknown"
        user: Optional[str] = None
        raw = ""
        try:
            msgs = getattr(f, "messages", []) or []
            if msgs:
                m0 = msgs[0]
                raw = str(m0.get("content") or "")
                name = str(m0.get("name") or "")
                if name.startswith("voice:"):
                    origin = "voice"
                elif name.startswith("twitch:"):
                    origin = "twitch"
                    user = name.split(":", 1)[1] or None
        except Exception:
            pass
        return origin, user, raw

    async def _release_next_if_idle(self) -> None:
        if self._busy or self._current is not None:
            return

        # fairness: after N voice turns, force one twitch turn if available
        pick_twitch = False
        if self._voices_since_last_twitch >= self._fairness_after_voice and self._twitch_q:
            pick_twitch = True

        item: Optional[_QueuedTurn] = None
        if pick_twitch:
            item = self._twitch_q.popleft()
        elif self._voice_q:
            item = self._voice_q.popleft()
        elif self._twitch_q:
            item = self._twitch_q.popleft()

        if not item:
            return

        # Mark busy & publish metadata
        self._current = item
        self._busy = True
        try:
            # Ensure release has run_llm=True
            item.frame.run_llm = True
        except Exception:
            pass

        self.state.set_current_turn(origin=item.origin, user=item.user)

        logger.log(
            "TURN",
            f"release origin={item.origin} user={item.user} raw='{item.raw[:80]}'",
        )
        await self.push_frame(item.frame, FrameDirection.DOWNSTREAM)

        # Arm watchdog in case downstream providers hang
        self._arm_watchdog()

    async def _finish_current_turn(self) -> None:
        self._cancel_watchdog()
        if self._current:
            if self._current.origin == "voice":
                self._voices_since_last_twitch += 1
            elif self._current.origin == "twitch":
                self._voices_since_last_twitch = 0
        self._current = None
        self._busy = False
        self.state.clear_current_turn()
        await self._release_next_if_idle()

    def _arm_watchdog(self) -> None:
        self._cancel_watchdog()
        self._timeout_task = asyncio.create_task(self._watchdog())

    def _cancel_watchdog(self) -> None:
        if self._timeout_task:
            try:
                self._timeout_task.cancel()
            except Exception:
                pass
            self._timeout_task = None

    async def _watchdog(self) -> None:
        try:
            await asyncio.sleep(self._timeout_secs)
            logger.warning(
                f"Turn watchdog expired after {self._timeout_secs}s; forcing release"
            )
            await self._finish_current_turn()
        except asyncio.CancelledError:  # normal when turn finishes in time
            pass
