"""Helper to create STTMuteFilter with desired strategy.

Encapsulates library import and default strategy selection in one place.
"""

from __future__ import annotations

from pipecat.processors.filters.stt_mute_filter import (
    STTMuteFilter,
    STTMuteConfig,
    STTMuteStrategy,
)


def create_stt_mute_filter() -> STTMuteFilter:
    """Create a mute filter that always mutes STT during bot speech."""
    return STTMuteFilter(
        config=STTMuteConfig(strategies={STTMuteStrategy.ALWAYS})
    )


