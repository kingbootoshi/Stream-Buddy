"""Event handlers for pipeline frames and overlay synchronization."""

from __future__ import annotations

from loguru import logger

from pipecat.frames.frames import (
    TextFrame,
    LLMMessagesFrame,
    LLMFullResponseStartFrame,
    LLMFullResponseEndFrame,
    TTSStartedFrame,
    TTSStoppedFrame,
    OutputAudioRawFrame,
    InterimTranscriptionFrame,
    TranscriptionFrame,
)

from ..core.state import SharedState
from ..api.events import OverlayEventBus


def register_handlers(task, state: SharedState, bus: OverlayEventBus) -> None:
    """Wire up downstream/upstream logging and overlay events."""

    @task.event_handler("on_frame_reached_upstream")
    async def _log_upstream_frames(_, frame):  # noqa: D401
        if isinstance(frame, LLMMessagesFrame):
            logger.info("LLM request → OpenRouter (LLMMessagesFrame)")

    @task.event_handler("on_frame_reached_downstream")
    async def _log_downstream_frames(_, frame):  # noqa: D401
        if isinstance(frame, TextFrame):
            logger.info(f"Text: {getattr(frame, 'text', '')}")
        elif isinstance(frame, LLMFullResponseStartFrame):
            logger.info("LLM response started")
        elif isinstance(frame, LLMFullResponseEndFrame):
            logger.info("LLM response ended")
        elif isinstance(frame, TTSStartedFrame):
            logger.info("TTS synthesis started (→ ElevenLabs)")
        elif isinstance(frame, OutputAudioRawFrame):
            logger.debug("Received TTS audio frame")
        elif isinstance(frame, TTSStoppedFrame):
            logger.info("TTS synthesis finished")
        elif isinstance(frame, InterimTranscriptionFrame):
            expected_muted = (not state.listening) or bool(state.tts_speaking)
            if expected_muted:
                logger.warning(
                    "Received STT interim while muted",
                    extra={
                        "text": getattr(frame, "text", ""),
                        "listening": state.listening,
                        "tts_speaking": state.tts_speaking,
                    },
                )
            else:
                logger.info(f"STT interim: {getattr(frame, 'text', '')}")
        elif isinstance(frame, TranscriptionFrame):
            expected_muted = (not state.listening) or bool(state.tts_speaking)
            if expected_muted:
                logger.warning(
                    "Received STT final while muted",
                    extra={
                        "text": getattr(frame, "text", ""),
                        "listening": state.listening,
                        "tts_speaking": state.tts_speaking,
                    },
                )
            else:
                logger.info(f"STT final : {getattr(frame, 'text', '')}")

    # Set filters to limit handler invocation to interesting frames
    from pipecat.frames.frames import (
        LLMMessagesFrame as _U,
        TextFrame as _T,
        LLMFullResponseStartFrame as _RS,
        LLMFullResponseEndFrame as _RE,
        TTSStartedFrame as _TS,
        OutputAudioRawFrame as _OA,
        TTSStoppedFrame as _TE,
        InterimTranscriptionFrame as _IT,
        TranscriptionFrame as _TF,
    )

    task.set_reached_upstream_filter((_U,))
    task.set_reached_downstream_filter((_T, _RS, _RE, _TS, _OA, _TE, _IT, _TF))

    # Overlay sync: toggle speaking in state and broadcast events
    @task.event_handler("on_frame_reached_downstream")
    async def _signal_overlay(_, frame):  # noqa: D401
        if isinstance(frame, TTSStartedFrame):
            state.set_tts_speaking(True)
            await bus.on_tts_started(state.current_mood)
        elif isinstance(frame, TTSStoppedFrame):
            state.set_tts_speaking(False)
            await bus.on_tts_stopped()


