from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import uuid4

from .chat_agent import ChatModelNotConfiguredError
from .chat_models import (
    ChatAgentResult,
    ChatHistoryResponse,
    ChatMessage,
    ChatMessageResponse,
    ChatRole,
    ChatSession,
)
from .domain import AnalysisResponse, BatchAnalysisResponse, CounterpartyCard
from .repositories import CounterpartyRepository


class ChatSessionNotFoundError(LookupError):
    pass


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


class ChatSessionStore(Protocol):
    async def create(
        self, inns: list[str], analyses: dict[str, AnalysisResponse]
    ) -> ChatSession: ...

    async def get(self, chat_id: str) -> ChatSession | None: ...

    async def append_messages(
        self, chat_id: str, messages: list[ChatMessage]
    ) -> None: ...

    async def ensure_indexes(self) -> None: ...


class InMemoryChatSessionStore:
    def __init__(self, ttl_seconds: int) -> None:
        self.ttl = timedelta(seconds=ttl_seconds)
        self._sessions: dict[str, ChatSession] = {}
        self._lock = asyncio.Lock()

    async def create(
        self, inns: list[str], analyses: dict[str, AnalysisResponse]
    ) -> ChatSession:
        now = datetime.now(UTC)
        session = ChatSession(
            chat_id=str(uuid4()),
            inns=inns,
            analyses=analyses,
            created_at=now,
            expires_at=now + self.ttl,
        )
        async with self._lock:
            self._sessions[session.chat_id] = session
        return session

    async def get(self, chat_id: str) -> ChatSession | None:
        async with self._lock:
            session = self._sessions.get(chat_id)
            if session is not None and session.expires_at > datetime.now(UTC):
                return session.model_copy(deep=True)
            self._sessions.pop(chat_id, None)
        return None

    async def append_messages(self, chat_id: str, messages: list[ChatMessage]) -> None:
        async with self._lock:
            session = self._sessions.get(chat_id)
            if session is None or session.expires_at <= datetime.now(UTC):
                self._sessions.pop(chat_id, None)
                raise ChatSessionNotFoundError(chat_id)
            session.messages.extend(messages)

    async def ensure_indexes(self) -> None:
        return None


class MongoChatSessionStore:
    def __init__(self, collection: Any, ttl_seconds: int) -> None:
        self.collection = collection
        self.ttl = timedelta(seconds=ttl_seconds)

    async def ensure_indexes(self) -> None:
        await self.collection.create_index(
            "expires_at",
            expireAfterSeconds=0,
            name="chat_session_ttl",
        )

    async def create(
        self, inns: list[str], analyses: dict[str, AnalysisResponse]
    ) -> ChatSession:
        now = datetime.now(UTC)
        session = ChatSession(
            chat_id=str(uuid4()),
            inns=inns,
            analyses=analyses,
            created_at=now,
            expires_at=now + self.ttl,
        )
        document = session.model_dump(mode="json")
        document["created_at"] = session.created_at
        document["expires_at"] = session.expires_at
        document["_id"] = session.chat_id
        await self.collection.insert_one(document)
        return session

    async def get(self, chat_id: str) -> ChatSession | None:
        document = await self.collection.find_one(
            {
                "_id": chat_id,
                "expires_at": {"$gt": datetime.now(UTC)},
            },
            projection={"_id": False},
        )
        if document is None:
            return None
        return ChatSession.model_validate(document)

    async def append_messages(self, chat_id: str, messages: list[ChatMessage]) -> None:
        result = await self.collection.update_one(
            {
                "_id": chat_id,
                "expires_at": {"$gt": datetime.now(UTC)},
            },
            {
                "$push": {
                    "messages": {
                        "$each": [
                            message.model_dump(mode="python") for message in messages
                        ]
                    }
                }
            },
        )
        if result.matched_count == 0:
            raise ChatSessionNotFoundError(chat_id)


class ChatService:
    def __init__(
        self,
        repository: CounterpartyRepository,
        store: ChatSessionStore,
        agent: ChatResponder,
        timeout_seconds: float,
        history_limit: int,
    ) -> None:
        self.repository = repository
        self.store = store
        self.agent = agent
        self.timeout_seconds = timeout_seconds
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
            async with asyncio.timeout(self.timeout_seconds):
                result = await self.agent.answer(
                    question,
                    cards,
                    session.analyses,
                    history,
                )
        except ChatModelNotConfiguredError:
            raise
        except TimeoutError:
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
