from __future__ import annotations

import httpx2
from pydantic_ai.providers.openrouter import OpenRouterProvider


def openrouter_provider(api_key: str) -> OpenRouterProvider:
    """Build an OpenRouter provider without a client-side request deadline."""
    return OpenRouterProvider(
        api_key=api_key,
        http_client=httpx2.AsyncClient(timeout=None),
    )
