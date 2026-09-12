from __future__ import annotations

from collections.abc import Awaitable, Callable

from counterparty_verification.agents.reputation import aggregate_reputation
from counterparty_verification.analysis.rules.finance import FinanceView
from counterparty_verification.analysis.rules.finance import (
    build_view as build_finance_view,
)
from counterparty_verification.analysis.rules.finance import (
    run_checks as run_finance_checks,
)
from counterparty_verification.analysis.rules.general import GeneralView
from counterparty_verification.analysis.rules.general import (
    build_view as build_general_view,
)
from counterparty_verification.analysis.rules.general import (
    run_checks as run_general_checks,
)
from counterparty_verification.analysis.rules.legal import LegalView
from counterparty_verification.analysis.rules.legal import (
    build_view as build_legal_view,
)
from counterparty_verification.analysis.rules.legal import (
    run_checks as run_legal_checks,
)
from counterparty_verification.analysis.rules.procurement import ProcurementView
from counterparty_verification.analysis.rules.procurement import (
    build_view as build_procurement_view,
)
from counterparty_verification.analysis.rules.procurement import (
    run_checks as run_procurement_checks,
)
from counterparty_verification.analysis.rules.procurement import _qty as _amount
from counterparty_verification.analysis.rules.reputation import (
    build_view as build_reputation_view,
)
from counterparty_verification.analysis.rules.structure import (
    LegalForm,
    StructureView,
    build_view,
    run_checks,
)
from counterparty_verification.domain import (
    ChapterResult,
    CounterpartyCard,
    Evidence,
    Observation,
    RiskLevel,
)


def _general_conclusion(view: GeneralView, observations: list[Observation]) -> str:
    report = view.report
    name = report.full_name or report.short_name or "Организация"
    parts = [f"{name}: статус {report.status or 'не указан'}."]
    if observations:
        titles = "; ".join(item.title.lower() for item in observations)
        parts.append(f"Стоит обратить внимание: {titles}.")
    else:
        parts.append("По общим сведениям вопросов, требующих внимания, не найдено.")
    return " ".join(parts)


def analyze_general(card: CounterpartyCard) -> ChapterResult:
    """Describes registration status and provider-assigned risk markers.

    The chapter deliberately assigns no risk level: it lists observations with
    the fields they came from, and the verdict is left to the analyst.
    """
    view = build_general_view(card)
    observations = run_general_checks(view)
    report = view.report
    evidence = [
        Evidence(field="company_reports.inn", value=report.inn),
        Evidence(field="company_reports.full_name", value=report.full_name),
        Evidence(field="company_reports.status", value=report.status),
    ]
    return ChapterResult(
        chapter="general",
        risk_level=RiskLevel.UNKNOWN,
        conclusion=_general_conclusion(view, observations),
        observations=observations,
        evidence=evidence,
    )


def analyze_structure(card: CounterpartyCard) -> ChapterResult:
    """Describes the ownership and management structure and what to look at.

    The chapter deliberately assigns no risk level: it lists observations with
    the fields they came from, and the verdict is left to the analyst.
    """
    view = build_view(card)
    observations = run_checks(view)
    sufficient = bool(view.founders or view.director or view.activities)
    return ChapterResult(
        chapter="structure",
        risk_level=RiskLevel.UNKNOWN,
        conclusion=(
            _structure_conclusion(view, observations)
            if sufficient
            else "Недостаточно данных об учредителях, руководстве и видах деятельности."
        ),
        observations=observations,
        evidence=_structure_evidence(view),
        data_sufficient=sufficient,
    )


def _structure_conclusion(view: StructureView, observations: list[Observation]) -> str:
    form = {
        LegalForm.SOLE_TRADER: "индивидуальный предприниматель",
        LegalForm.NON_PROFIT: "некоммерческая организация",
    }.get(view.legal_form, "коммерческая организация")
    director = view.director
    parts = [f"Форма: {form}."]
    if view.is_company:
        share = view.total_active_share
        share_text = f", суммарная доля {share:g}%" if share is not None else ""
        parts.append(f"Активных учредителей: {len(view.active_founders)}{share_text}.")
    else:
        parts.append("Уставный капитал и доли участия для этой формы не применяются.")
    if director is not None:
        position = director.item.position or "должность не указана"
        parts.append(f"Руководитель: {director.item.name or 'не указан'} ({position}).")
    elif view.parents:
        parts.append(f"Управляющая организация: {view.parents[0].label}.")
    else:
        parts.append("Руководитель: не указан.")
    parts.append(
        f"Видов деятельности: {len(view.activities)}, "
        f"связанных организаций: {len(view.related)}, "
        f"филиалов: {len(view.branches)}."
    )
    if observations:
        titles = "; ".join(item.title.lower() for item in observations)
        parts.append(f"Стоит обратить внимание: {titles}.")
    else:
        parts.append(
            "По структуре и руководству вопросов, требующих внимания, не найдено."
        )
    return " ".join(parts)


def _structure_evidence(view: StructureView) -> list[Evidence]:
    evidence = [
        Evidence(field="company_reports.ogrn", value=view.report.ogrn),
        Evidence(
            field="company_reports.share_capital", value=view.report.share_capital
        ),
        Evidence(
            field="company_reports.registration_date",
            value=str(view.report.registration_date)
            if view.report.registration_date
            else None,
        ),
    ]
    if view.director is not None:
        evidence.append(view.director.evidence("name"))
        evidence.append(view.director.evidence("position"))
    if view.main_activity is not None:
        evidence.append(view.main_activity.evidence("code"))
    return evidence


def analyze_legal(card: CounterpartyCard) -> ChapterResult:
    """Describes arbitration, enforcement, inspections and licenses.

    The chapter deliberately assigns no risk level: it lists observations with
    the fields they came from, and the verdict is left to the analyst.
    """
    view = build_legal_view(card)
    observations = run_legal_checks(view)
    sufficient = bool(card.arbitration or card.legal_events)
    return ChapterResult(
        chapter="legal",
        risk_level=RiskLevel.UNKNOWN,
        conclusion=(
            _legal_conclusion(view, observations)
            if sufficient
            else "Недостаточно данных для анализа юридических рисков."
        ),
        observations=observations,
        evidence=_legal_evidence(view),
        data_sufficient=sufficient,
    )


def _legal_conclusion(view: LegalView, observations: list[Observation]) -> str:
    name = view.report.full_name or view.report.short_name or "Организация"
    parts = [
        (
            f"{name}: исполнительных производств {len(view.executions)} "
            f"(активных {len(view.active_executions)}), "
            f"проверок {len(view.inspections)}, лицензий {len(view.licenses)}."
        )
    ]
    pending = view.status_bucket("defendant", "pending")
    appealed = view.status_bucket("defendant", "appealed")
    if pending.has_cases or appealed.has_cases:
        parts.append(
            f"Открытых дел ответчика: {pending.count}, обжалованных: {appealed.count}."
        )
    if observations:
        titles = "; ".join(item.title.lower() for item in observations)
        parts.append(f"Стоит обратить внимание: {titles}.")
    else:
        parts.append("По юридическим рискам вопросов, требующих внимания, не найдено.")
    return " ".join(parts)


def _legal_evidence(view: LegalView) -> list[Evidence]:
    evidence = [
        Evidence(field="company_reports.inn", value=view.report.inn),
        Evidence(
            field="company_reports.report_date",
            value=str(view.report.report_date) if view.report.report_date else None,
        ),
    ]
    common = view.common_arbitration
    if common is not None:
        evidence.append(common.evidence("case_count"))
        evidence.append(common.evidence("amount"))
    proceeds = view.finance_evidence("proceeds")
    if proceeds is not None:
        evidence.append(proceeds)
    return evidence


def analyze_reputation(card: CounterpartyCard) -> ChapterResult:
    """Aggregates and highlights positive and negative reputation factors.

    `risk_factors` already arrives as free-form text pre-labelled by the
    data provider, so there is nothing left to threshold-check — only to
    group by chapter. This is fully deterministic
    (`agents.reputation.aggregate_reputation`); no model call is involved.
    The chapter assigns no verdict: `risk_level` is always `UNKNOWN` and
    findings live in `observations`, not `factors`.
    """
    view = build_reputation_view(card)
    sufficient = bool(view.indexed)
    observations = aggregate_reputation(view) if sufficient else []
    negative_chapters = {entry.chapter for entry in view.negative}
    positive_chapters = {entry.chapter for entry in view.positive}
    return ChapterResult(
        chapter="reputation",
        risk_level=RiskLevel.UNKNOWN,
        conclusion=(
            f"Негативных факторов: {len(view.negative)} "
            f"({len(negative_chapters)} раздел(ов)), позитивных: "
            f"{len(view.positive)} ({len(positive_chapters)} раздел(ов))."
            if sufficient
            else "Репутационные факторы в отчёте отсутствуют."
        ),
        observations=observations,
        evidence=[entry.evidence("name") for entry in view.indexed],
        data_sufficient=sufficient,
    )


def _finance_conclusion(view: FinanceView, observations: list[Observation]) -> str:
    latest = view.latest
    parts = [
        f"Отчётность за {len(view.reports)} год(лет), последний отчётный год — "
        f"{latest.item.year}."
    ]
    if observations:
        titles = "; ".join(item.title.lower() for item in observations)
        parts.append(f"Стоит обратить внимание: {titles}.")
    else:
        parts.append(
            "По финансовым показателям вопросов, требующих внимания, не найдено."
        )
    return " ".join(parts)


def _finance_evidence(view: FinanceView) -> list[Evidence]:
    latest = view.latest
    if latest is None:
        return []
    return [
        latest.evidence(name)
        for name in (
            "year",
            "proceeds",
            "profit",
            "total_assets",
            "total_liabilities",
            "capitals",
        )
    ]


def analyze_finance(card: CounterpartyCard) -> ChapterResult:
    """Describes revenue, profit and balance-sheet indicators, and what to look at.

    The chapter deliberately assigns no risk level: it lists observations with
    the fields they came from, and the verdict is left to the analyst.
    """
    view = build_finance_view(card)
    observations = run_finance_checks(view)
    sufficient = bool(view.reports)
    return ChapterResult(
        chapter="finance",
        risk_level=RiskLevel.UNKNOWN,
        conclusion=(
            _finance_conclusion(view, observations)
            if sufficient
            else "Финансовые данные отсутствуют."
        ),
        observations=observations,
        evidence=_finance_evidence(view),
        data_sufficient=sufficient,
    )


def _procurement_conclusion(
    view: ProcurementView, observations: list[Observation]
) -> str:
    signed_count = sum(agg.signed_count for agg in view.by_year.values())
    signed_amount = sum(agg.signed_amount for agg in view.by_year.values())
    parts = [
        f"Госзакупки за {len(view.years)} год(лет), подписано контрактов: "
        f"{signed_count} на сумму {_amount(signed_amount)} ₽."
    ]
    if observations:
        titles = "; ".join(item.title.lower() for item in observations)
        parts.append(f"Стоит обратить внимание: {titles}.")
    else:
        parts.append("По истории госзакупок вопросов, требующих внимания, не найдено.")
    return " ".join(parts)


def _procurement_evidence(view: ProcurementView) -> list[Evidence]:
    latest = view.latest_year
    if latest is None:
        return []
    return latest.evidence(
        "year",
        "federal_law_code",
        "tender_admitted_count",
        "tender_winner_count",
        "contract_signed_count",
        "contract_signed_amount",
    )


def analyze_procurement(card: CounterpartyCard) -> ChapterResult:
    """Describes public-procurement history and what to look at.

    The chapter deliberately assigns no risk level: it lists observations with
    the fields they came from, and the verdict is left to the analyst.
    """
    view = build_procurement_view(card)
    observations = run_procurement_checks(view)
    sufficient = bool(card.procurements)
    return ChapterResult(
        chapter="procurement",
        risk_level=RiskLevel.UNKNOWN,
        conclusion=(
            _procurement_conclusion(view, observations)
            if sufficient
            else "Данные о госзакупках отсутствуют."
        ),
        observations=observations,
        evidence=_procurement_evidence(view),
        data_sufficient=sufficient,
    )


ANALYZERS: dict[
    str, Callable[[CounterpartyCard], ChapterResult | Awaitable[ChapterResult]]
] = {
    "analyze_general": analyze_general,
    "analyze_structure": analyze_structure,
    "analyze_legal": analyze_legal,
    "analyze_reputation": analyze_reputation,
    "analyze_finance": analyze_finance,
    "analyze_procurement": analyze_procurement,
}
