from __future__ import annotations

import json
from typing import Any, Protocol

from fastmcp import Client
from tenacity import retry, stop_after_attempt, wait_fixed

from .analyzers import ANALYZERS
from .domain import ChapterResult, CounterpartyCard


class AnalysisToolClient(Protocol):
    async def call(self, tool_name: str, card: CounterpartyCard) -> ChapterResult: ...


class HttpMcpAnalysisClient:
    def __init__(self, url: str, timeout_seconds: float = 30) -> None:
        self.url = url
        self.timeout_seconds = timeout_seconds

    @retry(stop=stop_after_attempt(2), wait=wait_fixed(0.2), reraise=True)
    async def call(self, tool_name: str, card: CounterpartyCard) -> ChapterResult:
        async with Client(self.url, timeout=self.timeout_seconds) as client:
            result = await client.call_tool(
                tool_name,
                {"card": card.model_dump(mode="json")},
                timeout=self.timeout_seconds,
            )
        payload = getattr(result, "data", None)
        if payload is None:
            payload = getattr(result, "structured_content", None)
        if payload is None:
            text = "".join(
                getattr(item, "text", "") for item in getattr(result, "content", [])
            )
            payload = json.loads(text)
        return ChapterResult.model_validate(payload)


class LocalAnalysisToolClient:
    """In-process adapter for tests and development without the MCP process."""

    async def call(self, tool_name: str, card: CounterpartyCard) -> ChapterResult:
        return ANALYZERS[tool_name](card)
