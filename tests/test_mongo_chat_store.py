from copy import deepcopy
from datetime import UTC, datetime

import pytest

from counterparty_verification.chat_models import (
    ChatMessage,
    ChatRole,
)
from counterparty_verification.chat_service import MongoChatSessionStore
from counterparty_verification.domain import AnalysisResponse, RiskLevel


class UpdateResult:
    def __init__(self, matched_count: int) -> None:
        self.matched_count = matched_count


class FakeCollection:
    def __init__(self) -> None:
        self.document = None
        self.indexes = []

    async def create_index(self, field, **kwargs):
        self.indexes.append((field, kwargs))

    async def insert_one(self, document):
        self.document = deepcopy(document)

    async def find_one(self, query, projection):
        if self.document is None or self.document["_id"] != query["_id"]:
            return None
        document = deepcopy(self.document)
        if projection == {"_id": False}:
            document.pop("_id", None)
        return document

    async def update_one(self, query, update):
        if self.document is None or self.document["_id"] != query["_id"]:
            return UpdateResult(0)
        self.document["messages"].extend(
            deepcopy(update["$push"]["messages"]["$each"])
        )
        return UpdateResult(1)


@pytest.mark.asyncio
async def test_mongo_chat_store_persists_session_and_messages() -> None:
    collection = FakeCollection()
    store = MongoChatSessionStore(collection, ttl_seconds=60)
    analysis = AnalysisResponse(
        analysis_id="analysis-1",
        inn="7707083893",
        summary="Саммари",
        risk_level=RiskLevel.LOW,
        chapters=[],
    )

    await store.ensure_indexes()
    session = await store.create([analysis.inn], {analysis.inn: analysis})
    loaded = await store.get(session.chat_id)

    assert collection.indexes == [
        (
            "expires_at",
            {"expireAfterSeconds": 0, "name": "chat_session_ttl"},
        )
    ]
    assert loaded is not None
    assert loaded.inns == [analysis.inn]
    assert loaded.analyses[analysis.inn] == analysis

    message = ChatMessage(
        message_id="message-1",
        role=ChatRole.USER,
        content="Вопрос",
        created_at=datetime.now(UTC),
    )
    await store.append_messages(session.chat_id, [message])
    loaded = await store.get(session.chat_id)

    assert loaded is not None
    assert loaded.messages == [message]
