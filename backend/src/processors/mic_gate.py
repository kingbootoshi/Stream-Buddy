"""
MicGate: A Pipecat FrameProcessor to enforce true push-to-talk muting.

Why: Pipecat's stock filters always pass System frames; mic audio and VAD are
System frames (e.g., InputAudioRawFrame, UserStartedSpeakingFrame). To prevent
audio reaching STT when muted, we must drop those frames pre-STT via a custom
processor.

Behavior:
- Drops InputAudioRawFrame and VAD/Interruption frames while muted
- Forwards lifecycle frames (Start/End/Cancel/Stop)
- Forwards all other frames unchanged
- Muted when listening is OFF or TTS is speaking

Logging: emits concise debug logs for drops/allows with current state flags.
"""

from __future__ import annotations

from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.frames.frames import (
    StartFrame,
    EndFrame,
    CancelFrame,
    StopFrame,
    InputAudioRawFrame,
    StartInterruptionFrame,
    StopInterruptionFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
)
from loguru import logger


class MicGate(FrameProcessor):
    """Hard gate for mic input and VAD frames based on listening and TTS state."""

    def __init__(self, should_allow_callable):
        super().__init__()
        self._should_allow = should_allow_callable

    async def process_frame(self, frame, direction: FrameDirection):
        # Ensure base class sees StartFrame early so processor is marked started
        await super().process_frame(frame, direction)

        allowed = bool(self._should_allow())

        # Always forward lifecycle frames
        if isinstance(frame, (StartFrame, EndFrame, CancelFrame, StopFrame)):
            await self.push_frame(frame, direction)
            return

        # Gate only input/VAD/interruption frames
        if isinstance(
            frame,
            (
                InputAudioRawFrame,
                StartInterruptionFrame,
                StopInterruptionFrame,
                UserStartedSpeakingFrame,
                UserStoppedSpeakingFrame,
            ),
        ):
            if not allowed:
                logger.debug(f"MicGate dropped {frame.__class__.__name__}")
                return
            logger.debug(f"MicGate allowed {frame.__class__.__name__}")

        await self.push_frame(frame, direction)


