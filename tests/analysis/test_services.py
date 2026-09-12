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
    async def summarize(self, company_name, risk_level, chapters):
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


def second_card(card):
    return card.model_copy(
        update={
            "company_reports": card.company_reports.model_copy(
                update={"inn": "7816085851", "short_name": "Вторая компания"}
            )
        },
        deep=True,
    )


async def test_individual_and_comparison_summaries_run_concurrently(card):
    from counterparty_verification.analysis.service import TOOL_NAMES
    from counterparty_verification.domain import ChapterResult
    from tests.helpers import InMemoryRepository

    other = second_card(card)
    cards = [card, other]
    all_tools_started = asyncio.Event()
    all_models_started = asyncio.Event()
    started_tools = set()
    completed_tools = set()
    started_models = []
    compared_chapters = {}

    class Tools:
        async def call(self, name, supplied_card):
            key = (supplied_card.company_reports.inn, name)
            started_tools.add(key)
            if len(started_tools) == 12:
                all_tools_started.set()
            await all_tools_started.wait()
            completed_tools.add(key)
            return ChapterResult(
                chapter=name.removeprefix("analyze_"),
                conclusion=f"Tool result {key}",
            )

    async def meet(label):
        assert len(completed_tools) == 12
        started_models.append(label)
        if len(started_models) == 3:
            all_models_started.set()
        await all_models_started.wait()

    class Evaluator(StubEvaluator):
        async def summarize(self, name, risk, chapters):
            assert len(chapters) == len(TOOL_NAMES)
            await meet(name)
            return await super().summarize(name, risk, chapters)

    class Comparison:
        async def summarize(self, companies, chapters_by_inn):
            compared_chapters.update(chapters_by_inn)
            await meet("comparison")
            return "Общее саммари"

    service = AnalysisService(
        repository=InMemoryRepository(cards),
        tools=Tools(),
        evaluator=Evaluator(),
        sessions=InMemorySessionStore(60),
        comparison_agent=Comparison(),
    )
    inns = [other.company_reports.inn, "772377037026", card.company_reports.inn]
    async with asyncio.timeout(2):
        response = await service.analyze_many(inns)

    assert [item.inn for item in response.results] == inns
    assert response.results[1].status == BatchAnalysisStatus.NOT_FOUND
    assert response.comparison.summary == "Общее саммари"
    assert response.comparison.summary_error is None
    assert len(started_models) == 3
    assert len(started_tools) == 12
    for item in response.results:
        if item.analysis:
            assert compared_chapters[item.inn] is item.analysis.chapters or (
                compared_chapters[item.inn] == item.analysis.chapters
            )
            assert await service.sessions.get(item.analysis.analysis_id) is not None


@pytest.mark.parametrize("failure", ["individual", "comparison"])
async def test_summary_failure_keeps_other_results(card, failure):
    from tests.helpers import InMemoryRepository

    other = second_card(card)

    class Evaluator(StubEvaluator):
        async def summarize(self, name, risk, chapters):
            if failure == "individual" and name == other.company_reports.short_name:
                raise ConnectionError("model unavailable")
            return await super().summarize(name, risk, chapters)

    class Comparison:
        async def summarize(self, companies, chapters_by_inn):
            if failure == "comparison":
                raise ConnectionError("comparison unavailable")
            return "Общее саммари"

    service = AnalysisService(
        repository=InMemoryRepository([card, other]),
        tools=LocalAnalysisToolClient(),
        evaluator=Evaluator(),
        sessions=InMemorySessionStore(60),
        comparison_agent=Comparison(),
    )
    response = await service.analyze_many(
        [card.company_reports.inn, other.company_reports.inn]
    )
    assert all(item.status == BatchAnalysisStatus.SUCCESS for item in response.results)
    assert all(len(item.analysis.chapters) == 6 for item in response.results)
    if failure == "individual":
        assert "Автосводка без ИИ" in response.results[1].analysis.summary
        assert response.comparison.summary == "Общее саммари"
    else:
        assert response.comparison.summary is None
        assert response.comparison.summary_error
        assert all("LLM-саммари" in item.analysis.summary for item in response.results)


async def test_cancelling_batch_cancels_all_three_summaries(card):
    from tests.helpers import InMemoryRepository

    other = second_card(card)
    started = set()
    cancelled = set()
    ready = asyncio.Event()
    hold = asyncio.Event()

    async def wait_for_cancel(label):
        started.add(label)
        if len(started) == 3:
            ready.set()
        try:
            await hold.wait()
        except asyncio.CancelledError:
            cancelled.add(label)
            raise

    class Evaluator:
        async def summarize(self, name, risk, chapters):
            await wait_for_cancel(name)

    class Comparison:
        async def summarize(self, companies, chapters_by_inn):
            await wait_for_cancel("comparison")

    service = AnalysisService(
        repository=InMemoryRepository([card, other]),
        tools=LocalAnalysisToolClient(),
        evaluator=Evaluator(),
        sessions=InMemorySessionStore(60),
        comparison_agent=Comparison(),
    )
    task = asyncio.create_task(
        service.analyze_many([card.company_reports.inn, other.company_reports.inn])
    )
    try:
        async with asyncio.timeout(2):
            await ready.wait()
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert len(cancelled) == 3
    assert cancelled == started


async def test_single_found_company_does_not_call_comparison(card):
    class Comparison:
        async def summarize(self, *args):
            raise AssertionError("Comparison must not run for one company")

    service = build_service(StubRepository(card), LocalAnalysisToolClient())
    service.comparison_agent = Comparison()
    response = await service.analyze_many([card.company_reports.inn, "772377037026"])
    assert response.comparison is None
    assert response.results[0].analysis.summary
