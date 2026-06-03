"""LLM provider factory.

`get_provider()` returns the configured provider, defaulting to the offline
stub. The result is cached so we don't reconstruct SDK clients per request.
"""
from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.llm.base import (
    AxisScore,
    GeneratedQuestion,
    LLMProvider,
    ScoredAnswer,
)
from app.llm.stub import StubProvider

__all__ = [
    "LLMProvider",
    "GeneratedQuestion",
    "ScoredAnswer",
    "AxisScore",
    "StubProvider",
    "get_provider",
    "build_provider",
]


def build_provider() -> LLMProvider:
    """Construct a provider from current settings (uncached)."""
    settings = get_settings()
    if settings.llm_provider == "anthropic" and settings.anthropic_api_key:
        from app.llm.remote import AnthropicProvider

        return AnthropicProvider(settings.anthropic_api_key, settings.anthropic_model)
    if settings.llm_provider == "openai" and settings.openai_api_key:
        from app.llm.remote import OpenAIProvider

        return OpenAIProvider(settings.openai_api_key, settings.openai_model)
    return StubProvider()


@lru_cache(maxsize=1)
def get_provider() -> LLMProvider:
    return build_provider()
