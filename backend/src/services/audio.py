"""Audio transport setup using Pipecat local audio.

Provides factory helpers to create `LocalAudioTransport` and its params using
values from `Settings`.
"""

from __future__ import annotations

from typing import Tuple

from pipecat.transports.local.audio import (
    LocalAudioTransport,
    LocalAudioTransportParams,
)

from ..config.settings import Settings


def create_audio_transport(settings: Settings) -> Tuple[LocalAudioTransport, LocalAudioTransportParams]:
    """Create a local audio transport and parameters from settings.

    Returns a tuple `(transport, params)` so callers can reference both.
    """
    params = LocalAudioTransportParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
        audio_in_sample_rate=settings.audio_in_sample_rate,
        audio_out_sample_rate=settings.audio_out_sample_rate,
        audio_in_channels=settings.audio_in_channels,
        audio_out_channels=settings.audio_out_channels,
    )
    transport = LocalAudioTransport(params)
    return transport, params


