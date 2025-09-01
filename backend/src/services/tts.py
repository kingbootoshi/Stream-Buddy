"""TTS service factory."""

from __future__ import annotations

from pipecat.services.elevenlabs.tts import ElevenLabsTTSService

from ..config.settings import Settings


def create_tts_service(settings: Settings) -> ElevenLabsTTSService:
    """Create ElevenLabs streaming TTS with configured voice."""
    return ElevenLabsTTSService(api_key=settings.elevenlabs_api_key, voice_id=settings.voice_id)


