"""Producer helpers to normalize user text across branches.

Voice branch: capture final STT and transform to a canonical TextFrame that
matches the Twitch format intent (for consistent context aggregation).

Twitch branch: capture TextFrames emitted by TwitchChatSource.
"""

from __future__ import annotations

from pipecat.frames.frames import (
    Frame,
    TranscriptionFrame,
    TextFrame,
    LLMMessagesAppendFrame,
)
from loguru import logger
from pipecat.processors.producer_processor import ProducerProcessor


async def _is_final_transcription(frame: Frame) -> bool:
    return isinstance(frame, TranscriptionFrame)


async def _stt_to_llm_append(frame: Frame) -> Frame:
    if isinstance(frame, TranscriptionFrame):
        content = getattr(frame, "text", "") or ""
        # Prefix voice-originated content so the LLM can differentiate Bootoshi
        # from Twitch chat reliably. We keep the raw content unbracketed so it
        # reads naturally in conversation transcripts.
        text = f"[Bootoshi] says {content}"
        logger.info(f"<yellow>[VOICE->PRODUCER]</yellow> {text}")
        message = {"role": "user", "content": text, "name": "voice:bootoshi"}
        return LLMMessagesAppendFrame(messages=[message], run_llm=True)
    return frame


def make_voice_usertext_producer() -> ProducerProcessor:
    return ProducerProcessor(filter=_is_final_transcription, transformer=_stt_to_llm_append, passthrough=True)


async def _is_textframe(frame: Frame) -> bool:
    return isinstance(frame, TextFrame)


async def _twitch_text_to_llm_append(frame: Frame) -> Frame:
    if isinstance(frame, TextFrame):
        raw = getattr(frame, "text", "") or ""
        # Default to whole raw text as user content
        user_name = None
        content = raw
        # Parse canonical pattern: Twitch Chat User [NAME] says [MESSAGE]
        if raw.startswith("Twitch Chat User [") and "] says [" in raw and raw.endswith("]"):
            try:
                i0 = raw.index("[") + 1
                i1 = raw.index("]", i0)
                user_name = raw[i0:i1]
                j0 = raw.index("[", i1) + 1
                j1 = raw.rindex("]")
                content = raw[j0:j1]
            except Exception:
                # Fall back to raw
                content = raw
        # Prefix chat-originated content with a clear tag and username so the
        # LLM can address viewers directly and distinguish them from Bootoshi.
        if user_name:
            display = f"[CHAT] [{user_name}] says {content}"
        else:
            display = f"[CHAT] says {content}"

        message = {"role": "user", "content": display}
        if user_name:
            # Retain the structured name for downstream analytics/routing.
            message["name"] = f"twitch:{user_name}"
        # Ask the LLM to run for this appended message
        return LLMMessagesAppendFrame(messages=[message], run_llm=True)
    return frame


def make_twitch_usertext_producer() -> ProducerProcessor:
    # Transform Twitch TextFrame → LLMMessagesAppendFrame(run_llm=True)
    return ProducerProcessor(
        filter=_is_textframe,
        transformer=_twitch_text_to_llm_append,
        passthrough=True,
    )
