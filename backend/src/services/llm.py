"""LLM service factory and context aggregator."""

from __future__ import annotations

from typing import Tuple

from pipecat.services.openrouter.llm import OpenRouterLLMService
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext

from ..config.settings import Settings


def create_llm_service(settings: Settings) -> OpenRouterLLMService:
    """Create OpenRouter LLM service with headers and model from settings."""
    return OpenRouterLLMService(
        api_key=settings.openrouter_api_key,
        model=settings.openrouter_model,
        headers={"HTTP-Referer": settings.http_referer},
    )


def create_llm_context_and_aggregator(settings: Settings, llm: OpenRouterLLMService):
    """Create OpenAI-format context and corresponding aggregator from LLM.

    Returns `(context, aggregator)`.
    """
    context = OpenAILLMContext(
        messages=[{"role": "system", "content": settings.system_prompt}]
    )
    aggregator = llm.create_context_aggregator(context)
    return context, aggregator


