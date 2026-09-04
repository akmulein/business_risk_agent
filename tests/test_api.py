from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from counterparty_verification.agents import (
    EvaluatorAgent,
    QuestionAnswerAgent,
    SpecialistAgent,
)
from counterparty_verification.api import create_app
from counterparty_verification.mcp_client import LocalAnalysisToolClient
from counterparty_verification.repositories import JsonCounterpartyRepository
from counterparty_verification.services import (
    AnalysisService,
    InMemorySessionStore,
    QuestionService,
)
from counterparty_verification.settings import Settings


@pytest.fixture
def app():
    root = Path(__file__).parents[1]
    settings = Settings(
        openrouter_api_key=None,
        mock_data_path=root / "data" / "counterparties.json",
    )
    application = create_app(settings)
    sessions = InMemorySessionStore(60)
    application.state.analysis_service = AnalysisService(
        repository=JsonCounterpartyRepository(settings.mock_data_path),
        tools=LocalAnalysisToolClient(),
        specialist=SpecialistAgent(settings),
        evaluator=EvaluatorAgent(settings),
        sessions=sessions,
        timeout_seconds=5,
    )
    application.state.question_service = QuestionService(
        sessions, QuestionAnswerAgent(settings)
    )
    return application


@pytest.mark.asyncio
async def test_analysis_and_question_endpoints(app) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        analysis = await client.post(
            "/api/v1/analyses", json={"inns": ["7707083893"]}
        )
        assert analysis.status_code == 201
        body = analysis.json()["results"][0]["analysis"]
        assert body is not None
        assert body["summary"]
        assert len(body["chapters"]) == 6

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


@pytest.mark.asyncio
async def test_validation_and_not_found(app) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        invalid = await client.post(
            "/api/v1/analyses", json={"inns": ["123"]}
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
    assert missing.status_code == 201
    assert [item["status"] for item in missing.json()["results"]] == [
        "not_found",
        "not_found",
    ]
    assert too_many.status_code == 422


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
