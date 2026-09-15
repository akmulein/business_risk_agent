from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from app.chat.models import (
    ChatMessage,
    ChatSession,
)
from app.domain import (
    AnalysisResponse,
    CounterpartyCard,
)
from app.storage.interfaces import (
    ChatSessionNotFoundError,
)


@dataclass(slots=True)
class AnalysisSession:
    card: CounterpartyCard
    response: AnalysisResponse
    expires_at: datetime


class InMemorySessionStore:
    def __init__(self, ttl_seconds: int) -> None:
        self.ttl = timedelta(seconds=ttl_seconds)
        self._sessions: dict[str, AnalysisSession] = {}
        self._lock = asyncio.Lock()

    async def put(
        self, card: CounterpartyCard, response: AnalysisResponse
    ) -> AnalysisSession:
        session = AnalysisSession(
            card=card,
            response=response,
            expires_at=datetime.now(UTC) + self.ttl,
        )
        async with self._lock:
            self._sessions[response.analysis_id] = session
        return session

    async def get(self, analysis_id: str) -> AnalysisSession | None:
        async with self._lock:
            session = self._sessions.get(analysis_id)
            if session and session.expires_at > datetime.now(UTC):
                return session
            self._sessions.pop(analysis_id, None)
        return None


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

    async def clear_messages(self, chat_id: str) -> None:
        async with self._lock:
            session = self._sessions.get(chat_id)
            if session is None or session.expires_at <= datetime.now(UTC):
                self._sessions.pop(chat_id, None)
                raise ChatSessionNotFoundError(chat_id)
            session.messages.clear()

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

    async def clear_messages(self, chat_id: str) -> None:
        result = await self.collection.update_one(
            {
                "_id": chat_id,
                "expires_at": {"$gt": datetime.now(UTC)},
            },
            {"$set": {"messages": []}},
        )
        if result.matched_count == 0:
            raise ChatSessionNotFoundError(chat_id)
