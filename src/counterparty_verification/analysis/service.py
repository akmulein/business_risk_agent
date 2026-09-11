from __future__ import annotations

import asyncio
import logging
from uuid import uuid4

from counterparty_verification.agents.comparison import ComparisonAgent
from counterparty_verification.agents.evaluator import EvaluatorAgent
from counterparty_verification.analysis.comparison import build_comparison
from counterparty_verification.analysis.presentation import (
    build_company_profile,
    build_factor_summary,
    build_visualization_data,
)
from counterparty_verification.domain import (
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
from counterparty_verification.mcp.client import AnalysisToolClient
from counterparty_verification.storage.interfaces import CounterpartyRepository
from counterparty_verification.storage.sessions import InMemorySessionStore

TOOL_NAMES = (
    "analyze_general",
    "analyze_structure",
    "analyze_legal",
    "analyze_reputation",
    "analyze_finance",
    "analyze_procurement",
)

BATCH_ANALYSIS_CONCURRENCY = 3

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
        factor for factor in factors if factor.status in (RiskLevel.MEDIUM, RiskLevel.HIGH)
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
    return AnalysisSummary(risk_level=risk_level, summary=summary, key_factors=key_factors)


class AnalysisService:
    def __init__(
        self,
        repository: CounterpartyRepository,
        tools: AnalysisToolClient,
        evaluator: EvaluatorAgent,
        sessions: InMemorySessionStore,
        comparison_agent: ComparisonAgent | None = None,
    ) -> None:
        self.repository = repository
        self.tools = tools
        self.evaluator = evaluator
        self.sessions = sessions
        self.comparison_agent = comparison_agent

    async def analyze(self, inn: str) -> AnalysisResponse:
        card = await self.repository.get_by_inn(inn)
        if card is None:
            raise CounterpartyNotFoundError(inn)
        return await self._analyze_card(inn, card)

    async def analyze_many(self, inns: list[str]) -> BatchAnalysisResponse:
        cards = await self.repository.get_many_by_inns(inns)
        cards_by_inn = {card.company_reports.inn: card for card in cards}
        semaphore = asyncio.Semaphore(BATCH_ANALYSIS_CONCURRENCY)

        async def analyze_one(inn: str) -> BatchAnalysisItem:
            card = cards_by_inn.get(inn)
            if card is None:
                return BatchAnalysisItem(
                    inn=inn,
                    status=BatchAnalysisStatus.NOT_FOUND,
                    error="Контрагент с таким ИНН не найден",
                )
            async with semaphore:
                analysis = await self._analyze_card(inn, card)
            return BatchAnalysisItem(
                inn=inn,
                status=BatchAnalysisStatus.SUCCESS,
                analysis=analysis,
            )

        results = list(await asyncio.gather(*(analyze_one(inn) for inn in inns)))
        successful_cards = [
            cards_by_inn[item.inn]
            for item in results
            if item.status == BatchAnalysisStatus.SUCCESS and item.analysis is not None
        ]
        comparison = None
        if len(successful_cards) >= 2:
            comparison = build_comparison(successful_cards)
            try:
                if self.comparison_agent is None:
                    raise RuntimeError("Comparison agent is not configured")
                comparison.summary = await self.comparison_agent.summarize(
                    comparison.companies
                )
            except Exception:
                logger.exception("Comparison summary generation failed")
                comparison.summary_error = (
                    "Не удалось сформировать сравнительный анализ"
                )
        return BatchAnalysisResponse(results=results, comparison=comparison)

    async def _analyze_card(self, inn: str, card: CounterpartyCard) -> AnalysisResponse:
        chapters = await asyncio.gather(
            *(self._run_chapter(name, card) for name in TOOL_NAMES)
        )
        factor_summary = build_factor_summary(card, chapters)
        summary_factors = build_factor_summary(card, chapters, compact=False)
        bank_risk_level = card.company_reports.risk_level or RiskLevel.UNKNOWN
        company_name = (
            card.company_reports.short_name or card.company_reports.full_name or inn
        )
        try:
            summary = await self.evaluator.summarize(
                company_name,
                bank_risk_level,
                summary_factors,
            )
        except Exception:
            logger.exception(
                "Evaluator unavailable for inn=%s; using deterministic summary", inn
            )
            summary = _fallback_summary(company_name, bank_risk_level, summary_factors)
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
        await self.sessions.put(card, response)
        return response

    async def _run_chapter(
        self, tool_name: str, card: CounterpartyCard
    ) -> ChapterResult:
        chapter_name = tool_name.removeprefix("analyze_")
        try:
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
