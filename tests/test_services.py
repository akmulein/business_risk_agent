import asyncio

import pytest

from counterparty_verification.agents import EvaluatorAgent, SpecialistAgent
from counterparty_verification.domain import CounterpartyCard, RiskLevel
from counterparty_verification.mcp_client import LocalAnalysisToolClient
from counterparty_verification.services import (
    AnalysisService,
    CounterpartyNotFoundError,
    InMemorySessionStore,
)
from counterparty_verification.settings import Settings


class StubRepository:
    def __init__(self, card: CounterpartyCard | None) -> None:
        self.card = card
        self.requested: list[str] = []

    async def get_by_inn(self, inn: str) -> CounterpartyCard | None:
        self.requested.append(inn)
        return (
            self.card
            if self.card and self.card.company_reports.inn == inn
            else None
        )


class PartiallyFailingClient(LocalAnalysisToolClient):
    async def call(self, tool_name: str, card: CounterpartyCard):
        if tool_name == "analyze_reputation":
            raise ConnectionError("MCP unavailable")
        await asyncio.sleep(0)
        return await super().call(tool_name, card)


def build_service(repository, tools) -> AnalysisService:
    settings = Settings(openrouter_api_key=None)
    return AnalysisService(
        repository=repository,
        tools=tools,
        specialist=SpecialistAgent(settings),
        evaluator=EvaluatorAgent(settings),
        sessions=InMemorySessionStore(60),
        timeout_seconds=5,
    )


@pytest.mark.asyncio
async def test_analysis_reads_one_card_and_runs_all_chapters(
    card: CounterpartyCard,
) -> None:
    repository = StubRepository(card)
    service = build_service(repository, LocalAnalysisToolClient())

    response = await service.analyze(card.company_reports.inn)

    assert repository.requested == [card.company_reports.inn]
    assert len(response.chapters) == 6
    assert response.risk_level == RiskLevel.MEDIUM
    assert response.analysis_id


@pytest.mark.asyncio
async def test_analysis_returns_partial_report_when_one_tool_fails(
    card: CounterpartyCard,
) -> None:
    service = build_service(StubRepository(card), PartiallyFailingClient())

    response = await service.analyze(card.company_reports.inn)

    failed = next(item for item in response.chapters if item.chapter == "reputation")
    assert failed.error == "ConnectionError"
    assert failed.risk_level == RiskLevel.UNKNOWN


@pytest.mark.asyncio
async def test_missing_counterparty_raises() -> None:
    service = build_service(StubRepository(None), LocalAnalysisToolClient())

    with pytest.raises(CounterpartyNotFoundError):
        await service.analyze("7707083893")
