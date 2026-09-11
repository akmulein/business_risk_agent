from __future__ import annotations

import httpx2
from pydantic_ai.models.openrouter import OpenRouterModel
from pydantic_ai.providers.openrouter import OpenRouterProvider

from counterparty_verification.settings import Settings


# A stalled connection or a slow/unavailable upstream must not hang forever --
# without a bound here, callers (the evaluator, comparison, chat and
# question-answer agents) would wait indefinitely with no error at all.
OPENROUTER_TIMEOUT_SECONDS = 45.0


def openrouter_provider(api_key: str) -> OpenRouterProvider:
    """Build an OpenRouter provider with a bounded request timeout."""
    return OpenRouterProvider(
        api_key=api_key,
        http_client=httpx2.AsyncClient(timeout=OPENROUTER_TIMEOUT_SECONDS),
    )


def _model(settings: Settings) -> OpenRouterModel:
    if not settings.openrouter_api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not configured")
    return OpenRouterModel(
        settings.openrouter_model,
        provider=openrouter_provider(settings.openrouter_api_key),
    )
