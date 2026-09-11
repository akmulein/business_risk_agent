from typing import Any, Protocol

from counterparty_verification.chat.models import ChatMessage, ChatSession
from counterparty_verification.domain import AnalysisResponse, CounterpartyCard


class CounterpartyRepository(Protocol):
    async def get_by_inn(self, inn: str) -> CounterpartyCard | None: ...
    async def get_many_by_inns(self, inns: list[str]) -> list[CounterpartyCard]: ...
    async def get_source_report_by_inn(self, inn: str) -> dict[str, Any] | None: ...


class ChatSessionNotFoundError(LookupError):
    pass


class ChatSessionStore(Protocol):
    async def create(
        self, inns: list[str], analyses: dict[str, AnalysisResponse]
    ) -> ChatSession: ...

    async def get(self, chat_id: str) -> ChatSession | None: ...

    async def append_messages(
        self, chat_id: str, messages: list[ChatMessage]
    ) -> None: ...

    async def clear_messages(self, chat_id: str) -> None: ...

    async def ensure_indexes(self) -> None: ...
