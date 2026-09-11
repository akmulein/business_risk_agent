from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from counterparty_verification.agents.chat import ChatModelNotConfiguredError
from counterparty_verification.chat.models import (
    ChatAgentResult,
    ChatHistoryResponse,
    ChatMessage,
    ChatMessageResponse,
    ChatRole,
)
from counterparty_verification.domain import (
    AnalysisResponse,
    BatchAnalysisResponse,
    CounterpartyCard,
)
from counterparty_verification.storage.interfaces import (
    ChatSessionNotFoundError,
    ChatSessionStore,
    CounterpartyRepository,
)


class ChatUpstreamServiceError(RuntimeError):
    pass


class ChatResponder(Protocol):
    async def answer(
        self,
        question: str,
        cards: list[CounterpartyCard],
        analyses: dict[str, AnalysisResponse],
        history: list[ChatMessage],
    ) -> ChatAgentResult: ...


class ChatService:
    def __init__(
        self,
        repository: CounterpartyRepository,
        store: ChatSessionStore,
        agent: ChatResponder,
        history_limit: int,
    ) -> None:
        self.repository = repository
        self.store = store
        self.agent = agent
        self.history_limit = history_limit

    async def create_for_analysis(self, response: BatchAnalysisResponse) -> str | None:
        analyses: dict[str, AnalysisResponse] = {}
        inns: list[str] = []
        for item in response.results:
            if item.analysis is None or item.inn in analyses:
                continue
            analyses[item.inn] = item.analysis
            inns.append(item.inn)
        if not analyses:
            return None
        session = await self.store.create(inns, analyses)
        return session.chat_id

    async def answer(self, chat_id: str, question: str) -> ChatMessageResponse:
        session = await self.store.get(chat_id)
        if session is None:
            raise ChatSessionNotFoundError(chat_id)
        cards = await self.repository.get_many_by_inns(session.inns)
        if not cards:
            raise ChatSessionNotFoundError(chat_id)
        history = session.messages[-self.history_limit :] if self.history_limit else []
        try:
            result = await self.agent.answer(
                question,
                cards,
                session.analyses,
                history,
            )
        except ChatModelNotConfiguredError:
            raise
        except Exception as error:
            raise ChatUpstreamServiceError("Chat agent failed") from error

        now = datetime.now(UTC)
        messages = [
            ChatMessage(
                message_id=str(uuid4()),
                role=ChatRole.USER,
                content=question,
                created_at=now,
            ),
            ChatMessage(
                message_id=str(uuid4()),
                role=ChatRole.ASSISTANT,
                content=result.answer,
                sources=result.sources,
                created_at=datetime.now(UTC),
            ),
        ]
        await self.store.append_messages(chat_id, messages)
        return ChatMessageResponse(
            chat_id=chat_id,
            answer=result.answer,
            sources=result.sources,
        )

    async def history(self, chat_id: str) -> ChatHistoryResponse:
        session = await self.store.get(chat_id)
        if session is None:
            raise ChatSessionNotFoundError(chat_id)
        return ChatHistoryResponse(
            chat_id=chat_id,
            inns=session.inns,
            messages=session.messages,
        )

    async def clear_history(self, chat_id: str) -> ChatHistoryResponse:
        session = await self.store.get(chat_id)
        if session is None:
            raise ChatSessionNotFoundError(chat_id)
        await self.store.clear_messages(chat_id)
        return ChatHistoryResponse(chat_id=chat_id, inns=session.inns)
