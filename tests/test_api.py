from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from counterparty_verification.agents import (
    EvaluatorAgent,
    QuestionAnswerAgent,
    SpecialistAgent,
)
from counterparty_verification.api import create_app
from counterparty_verification.chat_models import (
    ChatAgentResult,
    ChatSource,
)
from counterparty_verification.chat_service import (
    ChatService,
    InMemoryChatSessionStore,
)
from counterparty_verification.mcp_client import LocalAnalysisToolClient
from counterparty_verification.repositories import JsonCounterpartyRepository
from counterparty_verification.services import (
    AnalysisService,
    InMemorySessionStore,
    QuestionService,
)
from counterparty_verification.settings import Settings


class StubChatAgent:
    async def answer(self, question, cards, analyses, history):
        inn = cards[0].company_reports.inn
        return ChatAgentResult(
            answer=f"Ответ по {len(cards)} контрагентам",
            sources=[
                ChatSource(
                    inn=inn,
                    field="company_reports.inn",
                    value=inn,
                )
            ],
        )


@pytest.fixture
def app():
    root = Path(__file__).parents[1]
    settings = Settings(
        openrouter_api_key=None,
        repository_backend="mock",
        mock_data_path=root / "data" / "counterparties.json",
    )
    repository = JsonCounterpartyRepository(settings.mock_data_path)
    application = create_app(settings)
    sessions = InMemorySessionStore(60)
    application.state.analysis_service = AnalysisService(
        repository=repository,
        tools=LocalAnalysisToolClient(),
        specialist=SpecialistAgent(settings),
        evaluator=EvaluatorAgent(settings),
        sessions=sessions,
        timeout_seconds=5,
    )
    application.state.question_service = QuestionService(
        sessions, QuestionAnswerAgent(settings)
    )
    application.state.chat_service = ChatService(
        repository=repository,
        store=InMemoryChatSessionStore(60),
        agent=StubChatAgent(),
        timeout_seconds=5,
        history_limit=12,
    )
    return application


@pytest.mark.asyncio
async def test_analysis_and_question_endpoints(app) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        analysis = await client.post("/api/v1/analyses", json={"inns": ["7707083893"]})
        assert analysis.status_code == 201
        analysis_body = analysis.json()
        chat_id = analysis_body["chat_id"]
        assert chat_id
        body = analysis_body["results"][0]["analysis"]
        assert body is not None
        assert body["summary"]
        assert len(body["chapters"]) == 6
        assert body["company_profile"]["inn"] == "7707083893"
        assert "financials" in body["visualization_data"]

        preview = await client.get("/api/v1/counterparties/7707083893/preview")
        assert preview.status_code == 200
        assert preview.json()["inn"] == "7707083893"
        assert preview.json()["name"]

        chat_answer = await client.post(
            f"/api/v1/chats/{chat_id}/messages",
            json={"message": "Какой ИНН указан в отчёте?"},
        )
        assert chat_answer.status_code == 200
        assert chat_answer.json()["answer"] == "Ответ по 1 контрагентам"
        assert chat_answer.json()["sources"][0]["value"] == "7707083893"

        history = await client.get(f"/api/v1/chats/{chat_id}/messages")
        assert history.status_code == 200
        assert len(history.json()["messages"]) == 2

        cleared = await client.delete(f"/api/v1/chats/{chat_id}/messages")
        assert cleared.status_code == 200
        assert cleared.json()["messages"] == []

        answer = await client.post(
            f"/api/v1/analyses/{body['analysis_id']}/questions",
            json={"question": "Какова прибыль?"},
        )
        assert answer.status_code == 200
        assert "OpenRouter не настроен" in answer.json()["answer"]

        isolated = await client.post(
            "/api/v1/analyses/not-this-session/questions",
            json={"question": "Какова прибыль?"},
        )
        assert isolated.status_code == 404

        missing_chat = await client.post(
            "/api/v1/chats/not-this-chat/messages",
            json={"message": "Вопрос"},
        )
        assert missing_chat.status_code == 404


@pytest.mark.asyncio
async def test_validation_and_not_found(app) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        invalid = await client.post("/api/v1/analyses", json={"inns": ["123"]})
        invalid_preview = await client.get("/api/v1/counterparties/123/preview")
        missing_preview = await client.get(
            "/api/v1/counterparties/1234567894/preview"
        )
        missing = await client.post(
            "/api/v1/analyses",
            json={"inns": ["1234567894", "772377037026"]},
        )
        too_many = await client.post(
            "/api/v1/analyses",
            json={"inns": ["7707083893"] * 11},
        )

    assert invalid.status_code == 422
    assert invalid_preview.status_code == 422
    assert missing_preview.status_code == 404
    assert missing.status_code == 201
    assert [item["status"] for item in missing.json()["results"]] == [
        "not_found",
        "not_found",
    ]
    assert too_many.status_code == 422

    assert missing.json()["chat_id"] is None


@pytest.mark.asyncio
async def test_multiple_inns_return_independent_results(app) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/analyses",
            json={"inns": ["7707083893", "772377037026"]},
        )

    assert response.status_code == 201
    body = response.json()
    assert body["chat_id"]
    assert [item["inn"] for item in body["results"]] == [
        "7707083893",
        "772377037026",
    ]
    assert body["results"][0]["status"] == "success"
    assert body["results"][0]["analysis"]["summary"]
    assert len(body["results"][0]["analysis"]["chapters"]) == 6
    assert body["results"][1] == {
        "inn": "772377037026",
        "status": "not_found",
        "analysis": None,
        "error": "Контрагент с таким ИНН не найден",
    }
