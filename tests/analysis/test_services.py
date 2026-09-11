import asyncio

import pytest

from counterparty_verification.analysis.service import (
    AnalysisService,
    CounterpartyNotFoundError,
)
from counterparty_verification.domain import (
    AnalysisSummary,
    BatchAnalysisStatus,
    CounterpartyCard,
    RiskLevel,
)
from counterparty_verification.mcp.client import LocalAnalysisToolClient
from counterparty_verification.storage.sessions import InMemorySessionStore


class StubRepository:
    def __init__(self, card: CounterpartyCard | None) -> None:
        self.card = card
        self.requested: list[str] = []
        self.requested_many: list[list[str]] = []

    async def get_by_inn(self, inn: str) -> CounterpartyCard | None:
        self.requested.append(inn)
        return self.card if self.card and self.card.company_reports.inn == inn else None

    async def get_many_by_inns(self, inns: list[str]) -> list[CounterpartyCard]:
        self.requested_many.append(inns)
        if self.card is None:
            return []
        if self.card.company_reports.inn not in inns:
            return []
        return [self.card]


class PartiallyFailingClient(LocalAnalysisToolClient):
    async def call(self, tool_name: str, card: CounterpartyCard):
        if tool_name == "analyze_reputation":
            raise ConnectionError("MCP unavailable")
        await asyncio.sleep(0)
        return await super().call(tool_name, card)


class StubEvaluator:
    async def summarize(self, company_name, risk_level, factors):
        return AnalysisSummary(
            risk_level=risk_level,
            summary=f"{company_name}: тестовое LLM-саммари",
        )


def build_service(repository, tools) -> AnalysisService:
    return AnalysisService(
        repository=repository,
        tools=tools,
        evaluator=StubEvaluator(),
        sessions=InMemorySessionStore(60),
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
    assert response.risk_level == (card.company_reports.risk_level or RiskLevel.UNKNOWN)
    assert response.factor_summary
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
async def test_chapter_preserves_tool_output_without_rewriting(card) -> None:
    original = await LocalAnalysisToolClient().call("analyze_general", card)

    class Tool:
        async def call(self, tool_name, supplied_card):
            return original

    service = build_service(StubRepository(card), Tool())
    chapter = await service._run_chapter("analyze_general", card)
    assert chapter is original


@pytest.mark.asyncio
async def test_missing_counterparty_raises() -> None:
    service = build_service(StubRepository(None), LocalAnalysisToolClient())

    with pytest.raises(CounterpartyNotFoundError):
        await service.analyze("7707083893")


@pytest.mark.asyncio
async def test_batch_analysis_keeps_input_order_and_missing_items(
    card: CounterpartyCard,
) -> None:
    repository = StubRepository(card)
    service = build_service(repository, LocalAnalysisToolClient())
    inns = [card.company_reports.inn, "772377037026"]

    response = await service.analyze_many(inns)

    assert repository.requested_many == [inns]
    assert [item.inn for item in response.results] == inns
    assert response.results[0].status == BatchAnalysisStatus.SUCCESS
    assert response.results[0].analysis is not None
    assert len(response.results[0].analysis.chapters) == 6
    assert response.results[1].status == BatchAnalysisStatus.NOT_FOUND
    assert response.results[1].analysis is None
    assert response.results[1].error


@pytest.mark.asyncio
async def test_six_tools_start_before_evaluator_runs(card):
    from counterparty_verification.analysis.service import TOOL_NAMES
    from counterparty_verification.domain import ChapterResult

    started = set()
    all_started = asyncio.Event()
    completed = set()

    class ConcurrentTools:
        async def call(self, name, supplied_card):
            started.add(name)
            if len(started) == len(TOOL_NAMES):
                all_started.set()
            await asyncio.wait_for(all_started.wait(), timeout=2)
            completed.add(name)
            return ChapterResult(chapter=name.removeprefix("analyze_"), conclusion=name)

    class Evaluator(StubEvaluator):
        calls = 0

        async def summarize(self, *args):
            assert completed == set(TOOL_NAMES)
            self.calls += 1
            return await super().summarize(*args)

    evaluator = Evaluator()
    service = AnalysisService(
        repository=StubRepository(card),
        tools=ConcurrentTools(),
        evaluator=evaluator,
        sessions=InMemorySessionStore(60),
    )
    response = await service.analyze(card.company_reports.inn)
    assert evaluator.calls == 1
    assert [chapter.conclusion for chapter in response.chapters] == list(TOOL_NAMES)
    assert all(chapter.error is None for chapter in response.chapters)
