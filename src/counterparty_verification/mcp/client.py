from __future__ import annotations

import inspect
import json
from typing import Protocol

from fastmcp import Client
from tenacity import retry, stop_after_attempt, wait_fixed

from counterparty_verification.analysis.analyzers import ANALYZERS
from counterparty_verification.domain import ChapterResult, CounterpartyCard


class AnalysisToolClient(Protocol):
    async def call(self, tool_name: str, card: CounterpartyCard) -> ChapterResult: ...


class HttpMcpAnalysisClient:
    def __init__(self, url: str) -> None:
        self.url = url
        # One Client for the process lifetime: fastmcp's Client reference-counts
        # nested `async with` entries and reuses the live session, so this avoids
        # paying a full MCP handshake on every single tool call.
        self._client = Client(url)

    @retry(stop=stop_after_attempt(2), wait=wait_fixed(0.2), reraise=True)
    async def call(self, tool_name: str, card: CounterpartyCard) -> ChapterResult:
        async with self._client as client:
            result = await client.call_tool(
                tool_name,
                {"card": card.model_dump(mode="json")},
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

    async def aclose(self) -> None:
        await self._client.close()


class LocalAnalysisToolClient:
    """In-process adapter for tests and development without the MCP process."""

    async def call(self, tool_name: str, card: CounterpartyCard) -> ChapterResult:
        result = ANALYZERS[tool_name](card)
        if inspect.isawaitable(result):
            result = await result
        return result
