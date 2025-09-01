"""STT service factory."""

from __future__ import annotations

from pipecat.services.assemblyai.stt import AssemblyAISTTService

from ..config.settings import Settings


def create_stt_service(settings: Settings) -> AssemblyAISTTService:
    """Create AssemblyAI STT service using configured API key."""
    return AssemblyAISTTService(api_key=settings.assemblyai_api_key)


