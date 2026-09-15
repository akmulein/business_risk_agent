from __future__ import annotations

import asyncio
import logging
from time import perf_counter
from uuid import uuid4

from app.agents.comparison import ComparisonAgent
from app.agents.evaluator import EvaluatorAgent
from app.analysis.comparison import build_comparison
from app.analysis.presentation import (
    build_company_profile,
    build_factor_summary,
    build_visualization_data,
)
from app.analysis.timing import record, timed
from app.domain import (
    AnalysisResponse,
    AnalysisSummary,
    BatchAnalysisItem,
    BatchAnalysisResponse,
    BatchAnalysisStatus,
    ChapterResult,
    CounterpartyCard,
    FactorSummaryItem,
    RiskLevel,
)
from app.mcp.client import AnalysisToolClient
from app.storage.interfaces import CounterpartyRepository
from app.storage.sessions import InMemorySessionStore

TOOL_NAMES = (
    "analyze_general",
    "analyze_structure",
    "analyze_legal",
    "analyze_reputation",
    "analyze_finance",
    "analyze_procurement",
)

logger = logging.getLogger(__name__)


class CounterpartyNotFoundError(LookupError):
    pass


class UpstreamServiceError(RuntimeError):
    pass


_RISK_LABELS_RU = {
    RiskLevel.LOW: "низкий",
    RiskLevel.MEDIUM: "средний",
    RiskLevel.HIGH: "высокий",
    RiskLevel.UNKNOWN: "не определён",
}


def _fallback_summary(
    company_name: str,
    risk_level: RiskLevel,
    factors: list[FactorSummaryItem],
) -> AnalysisSummary:
    """Deterministic stand-in for the evaluator when the LLM is unreachable
    or unconfigured, built only from what the rule-based chapters already
    computed -- no model call involved.
    """
    flagged = [
        factor
        for factor in factors
        if factor.status in (RiskLevel.MEDIUM, RiskLevel.HIGH)
    ]
    risk_label = _RISK_LABELS_RU[risk_level]
    if flagged:
        sections = ", ".join(factor.label for factor in flagged)
        summary = (
            f"Автосводка без ИИ: у компании «{company_name}» уровень риска "
            f"{risk_label}. Внимания требуют разделы: {sections}."
        )
    else:
        summary = (
            f"Автосводка без ИИ: у компании «{company_name}» уровень риска "
            f"{risk_label}. Разделы, требующие внимания, не выявлены."
        )
    key_factors = [detail for factor in flagged for detail in factor.details][:5]
    return AnalysisSummary(
        risk_level=risk_level, summary=summary, key_factors=key_factors
    )


class AnalysisService:
    def __init__(
        self,
        repository: CounterpartyRepository,
        tools: AnalysisToolClient,
        evaluator: EvaluatorAgent,
        sessions: InMemorySessionStore,
        comparison_agent: ComparisonAgent | None = None,
        chapter_concurrency: int = 10,
        llm_concurrency: int = 3,
    ) -> None:
        self.repository = repository
        self.tools = tools
        self.evaluator = evaluator
        self.sessions = sessions
        self.comparison_agent = comparison_agent
        self.chapter_concurrency = chapter_concurrency
        self.llm_concurrency = llm_concurrency

    async def analyze(self, inn: str) -> AnalysisResponse:
        card = await self.repository.get_by_inn(inn)
        if card is None:
            raise CounterpartyNotFoundError(inn)
        return await self._analyze_card(inn, card)

    async def analyze_many(self, inns: list[str]) -> BatchAnalysisResponse:
        record(
            "batch_config",
            chapter_concurrency=self.chapter_concurrency,
            llm_concurrency=self.llm_concurrency,
        )
        with timed("database", inns=inns):
            cards = await self.repository.get_many_by_inns(inns)
        cards_by_inn = {card.company_reports.inn: card for card in cards}

        # Depends only on the cards, not on any chapter/LLM result -- compute
        # it up front instead of waiting on anything.
        comparison = (
            build_comparison(list(cards_by_inn.values()))
            if len(cards_by_inn) >= 2
            else None
        )

        chapter_semaphore = asyncio.Semaphore(self.chapter_concurrency)
        llm_semaphore = asyncio.Semaphore(self.llm_concurrency)

        async def collect_one(card: CounterpartyCard) -> list[ChapterResult]:
            queued = perf_counter()
            async with chapter_semaphore:
                inn = card.company_reports.inn
                record(
                    "slot_acquired",
                    pool="chapters",
                    inn=inn,
                    wait_ms=(perf_counter() - queued) * 1000,
                )
                with timed("chapters", inn=inn):
                    return await self._collect_chapters(card)

        async def analyze_one(
            inn: str, chapter_tasks: dict[str, asyncio.Task[list[ChapterResult]]]
        ) -> BatchAnalysisItem:
            card = cards_by_inn.get(inn)
            if card is None:
                return BatchAnalysisItem(
                    inn=inn,
                    status=BatchAnalysisStatus.NOT_FOUND,
                    error="Контрагент с таким ИНН не найден",
                )
            chapters = await chapter_tasks[inn]
            queued = perf_counter()
            record("slot_queued", pool="llm", kind="individual", inn=inn)
            async with llm_semaphore:
                record(
                    "slot_acquired",
                    pool="llm",
                    kind="individual",
                    inn=inn,
                    wait_ms=(perf_counter() - queued) * 1000,
                )
                with timed("individual", inn=inn):
                    analysis = await self._build_analysis(inn, card, chapters)
            return BatchAnalysisItem(
                inn=inn,
                status=BatchAnalysisStatus.SUCCESS,
                analysis=analysis,
            )

        async def summarize_comparison(
            chapter_tasks: dict[str, asyncio.Task[list[ChapterResult]]],
        ) -> None:
            assert comparison is not None
            try:
                if self.comparison_agent is None:
                    raise RuntimeError("Comparison agent is not configured")
                chapters_by_inn = {
                    inn: await chapter_tasks[inn] for inn in cards_by_inn
                }
                queued = perf_counter()
                record("slot_queued", pool="llm", kind="comparison")
                async with llm_semaphore:
                    record(
                        "slot_acquired",
                        pool="llm",
                        kind="comparison",
                        wait_ms=(perf_counter() - queued) * 1000,
                    )
                    with timed("comparison"):
                        comparison.summary = await self.comparison_agent.summarize(
                            comparison.companies, chapters_by_inn
                        )
            except Exception:
                logger.exception("Comparison summary generation failed")
                comparison.summary_error = (
                    "Не удалось сформировать сравнительный анализ"
                )

        # Every summary consumes prepared tool results; no summary depends on
        # another model response. TaskGroup also cancels peers on cancellation.
        async with asyncio.TaskGroup() as group:
            chapter_tasks = {
                inn: group.create_task(collect_one(card))
                for inn, card in cards_by_inn.items()
            }
            tasks = [group.create_task(analyze_one(inn, chapter_tasks)) for inn in inns]
            if comparison is not None:
                group.create_task(summarize_comparison(chapter_tasks))

        return BatchAnalysisResponse(
            results=[task.result() for task in tasks], comparison=comparison
        )

    async def _collect_chapters(self, card: CounterpartyCard) -> list[ChapterResult]:
        return list(
            await asyncio.gather(
                *(self._run_chapter(name, card) for name in TOOL_NAMES)
            )
        )

    async def _analyze_card(self, inn: str, card: CounterpartyCard) -> AnalysisResponse:
        chapters = await self._collect_chapters(card)
        return await self._build_analysis(inn, card, chapters)

    async def _build_analysis(
        self, inn: str, card: CounterpartyCard, chapters: list[ChapterResult]
    ) -> AnalysisResponse:
        factor_summary = build_factor_summary(card, chapters)
        bank_risk_level = card.company_reports.risk_level or RiskLevel.UNKNOWN
        company_name = (
            card.company_reports.short_name or card.company_reports.full_name or inn
        )
        try:
            summary = await self.evaluator.summarize(
                company_name,
                bank_risk_level,
                chapters,
                build_comparison([card]).companies[0],
            )
        except Exception:
            logger.exception(
                "Evaluator unavailable for inn=%s; using deterministic summary", inn
            )
            summary = _fallback_summary(
                company_name,
                bank_risk_level,
                build_factor_summary(card, chapters, compact=False),
            )
        response = AnalysisResponse(
            analysis_id=str(uuid4()),
            inn=inn,
            summary=summary.summary,
            risk_level=summary.risk_level,
            chapters=chapters,
            factor_summary=factor_summary,
            company_profile=build_company_profile(card),
            visualization_data=build_visualization_data(card),
        )
        with timed("session_save", inn=inn):
            await self.sessions.put(card, response)
        return response

    async def _run_chapter(
        self, tool_name: str, card: CounterpartyCard
    ) -> ChapterResult:
        chapter_name = tool_name.removeprefix("analyze_")
        try:
            with timed("tool", tool=tool_name, inn=card.company_reports.inn):
                chapter = await self.tools.call(tool_name, card)
        except Exception as error:
            logger.exception("MCP analysis chapter failed: %s", chapter_name)
            return ChapterResult(
                chapter=chapter_name,
                risk_level=RiskLevel.UNKNOWN,
                conclusion=f"Раздел {chapter_name} временно недоступен.",
                data_sufficient=False,
                error=type(error).__name__,
            )
        return chapter
