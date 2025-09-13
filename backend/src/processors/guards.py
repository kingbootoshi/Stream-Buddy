"""Guard processors to enforce frame-type expectations in the LLM→TTS path.

DropRawTextBeforeLLM ensures raw TextFrame items do not flow into the LLM/TTS
tail. Aggregators sometimes forward TextFrames downstream while also emitting
LLM message/context frames upstream; those TextFrames should not reach LLM or
TTS (otherwise TTS may speak them verbatim).
"""

from __future__ import annotations

from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.frames.frames import TextFrame


class DropRawTextBeforeLLM(FrameProcessor):
    """Drops TextFrame in downstream direction to prevent bypassing LLM."""

    async def process_frame(self, frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if direction == FrameDirection.DOWNSTREAM and isinstance(frame, TextFrame):
            # Swallow raw text; LLM should be fed by LLMMessages/Context frames instead
            return
        await self.push_frame(frame, direction)

