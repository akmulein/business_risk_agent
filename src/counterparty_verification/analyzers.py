from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .domain import (
    ChapterResult,
    CounterpartyCard,
    Evidence,
    Observation,
    RiskFactor,
    RiskLevel,
)
from .legal_rules import LegalView
from .legal_rules import build_view as build_legal_view
from .legal_rules import run_checks as run_legal_checks
from .structure_rules import LegalForm, StructureView, build_view, run_checks


def _risk_max(*levels: RiskLevel) -> RiskLevel:
    rank = {
        RiskLevel.UNKNOWN: 0,
        RiskLevel.LOW: 1,
        RiskLevel.MEDIUM: 2,
        RiskLevel.HIGH: 3,
    }
    return max(levels, key=rank.get, default=RiskLevel.UNKNOWN)


def _factor(
    title: str, detail: str, severity: RiskLevel, field: str, value: Any
) -> RiskFactor:
    return RiskFactor(
        title=title,
        detail=detail,
        severity=severity,
        evidence=[Evidence(field=field, value=value)],
    )


def analyze_general(card: CounterpartyCard) -> ChapterResult:
    factors: list[RiskFactor] = []
    report = card.company_reports
    if report.status in {"CLOSED", "закрытая"}:
        factors.append(
            _factor(
                "Организация закрыта",
                report.status_reason or "В отчёте указан статус закрытой организации",
                RiskLevel.HIGH,
                "company_reports.status",
                report.status,
            )
        )
    if report.zsk_risk_level in {"YELLOW", "RED"}:
        factors.append(
            _factor(
                "Риск ЗСК",
                f"Уровень «Знай своего клиента»: {report.zsk_risk_level}",
                RiskLevel.HIGH
                if report.zsk_risk_level == "RED"
                else RiskLevel.MEDIUM,
                "company_reports.zsk_risk_level",
                report.zsk_risk_level,
            )
        )
    declared = report.risk_level
    if declared in {RiskLevel.MEDIUM, RiskLevel.HIGH}:
        factors.append(
            _factor(
                "Риск из исходного отчёта",
                f"Поставщик данных указал уровень {declared.value}",
                declared,
                "company_reports.risk_level",
                declared.value,
            )
        )
    risk = _risk_max(*(factor.severity for factor in factors), RiskLevel.LOW)
    name = report.full_name or report.short_name or "Организация"
    evidence = [
        Evidence(field="company_reports.inn", value=report.inn),
        Evidence(field="company_reports.full_name", value=report.full_name),
        Evidence(field="company_reports.status", value=report.status),
    ]
    return ChapterResult(
        chapter="general",
        risk_level=risk,
        conclusion=(
            f"{name}: статус {report.status or 'не указан'}, "
            f"общий риск {risk.value}."
        ),
        factors=factors,
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
            f"Открытых дел ответчика: {pending.count}, "
            f"обжалованных: {appealed.count}."
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
    negative = [item for item in card.risk_factors if item.sign == "negative"]
    positive = [item for item in card.risk_factors if item.sign == "positive"]
    factors = [
        _factor(
            item.name,
            f"Код: {item.code or 'не указан'}",
            RiskLevel.HIGH,
            "risk_factors",
            item.model_dump(mode="json"),
        )
        for item in negative
    ]
    sufficient = bool(negative or positive)
    return ChapterResult(
        chapter="reputation",
        risk_level=RiskLevel.HIGH if negative else (
            RiskLevel.LOW if sufficient else RiskLevel.UNKNOWN
        ),
        conclusion=(
            f"Негативных факторов: {len(negative)}, позитивных: {len(positive)}."
            if sufficient
            else "Репутационные факторы в отчёте отсутствуют."
        ),
        factors=factors,
        evidence=[
            Evidence(
                field="risk_factors",
                value=[item.model_dump(mode="json") for item in card.risk_factors],
            ),
        ],
        data_sufficient=sufficient,
    )


def analyze_finance(card: CounterpartyCard) -> ChapterResult:
    reports = sorted(card.financial_reports, key=lambda item: item.year)
    factors: list[RiskFactor] = []
    if reports:
        latest = reports[-1]
        profit = float(latest.profit or 0)
        if profit < 0:
            factors.append(
                _factor(
                    "Убыток",
                    f"Прибыль последнего отчётного года: {profit:g}.",
                    RiskLevel.HIGH,
                    "financial_reports.profit",
                    profit,
                )
            )
        if len(reports) > 1:
            previous = float(reports[-2].proceeds or 0)
            current = float(latest.proceeds or 0)
            if previous > 0 and current < previous:
                change = (current - previous) / previous * 100
                factors.append(
                    _factor(
                        "Снижение выручки",
                        f"Изменение к предыдущему периоду: {change:.1f}%.",
                        RiskLevel.MEDIUM,
                        "financial_reports.proceeds",
                        [item.model_dump(mode="json") for item in reports],
                    )
                )
    solvency = reports[-1].solvency if reports else None
    if solvency is not None and float(solvency) < 1:
        factors.append(
            _factor(
                "Низкий коэффициент платёжеспособности",
                f"Значение в отчёте: {solvency}.",
                RiskLevel.MEDIUM,
                "financial_reports.solvency",
                solvency,
            )
        )
    sufficient = bool(reports)
    risk = _risk_max(*(factor.severity for factor in factors), RiskLevel.LOW)
    return ChapterResult(
        chapter="finance",
        risk_level=risk if sufficient else RiskLevel.UNKNOWN,
        conclusion=(
            f"Финансовых факторов риска найдено: {len(factors)}."
            if sufficient
            else "Финансовые данные отсутствуют."
        ),
        factors=factors,
        evidence=[
            Evidence(
                field="financial_reports",
                value=[item.model_dump(mode="json") for item in reports],
            ),
        ],
        data_sufficient=sufficient,
    )


def analyze_procurement(card: CounterpartyCard) -> ChapterResult:
    signed_count = sum(
        int(item.contract_signed_count or 0) for item in card.procurements
    )
    signed_amount = sum(
        float(item.contract_signed_amount or 0) for item in card.procurements
    )
    sufficient = bool(card.procurements)
    return ChapterResult(
        chapter="procurement",
        risk_level=RiskLevel.LOW if sufficient else RiskLevel.UNKNOWN,
        conclusion=(
            f"Подписано госконтрактов: {signed_count}, сумма: {signed_amount:g}."
            if sufficient
            else "Данные о госзакупках отсутствуют."
        ),
        evidence=[
            Evidence(
                field="procurements",
                value=[item.model_dump(mode="json") for item in card.procurements],
            )
        ],
        data_sufficient=sufficient,
    )


ANALYZERS: dict[str, Callable[[CounterpartyCard], ChapterResult]] = {
    "analyze_general": analyze_general,
    "analyze_structure": analyze_structure,
    "analyze_legal": analyze_legal,
    "analyze_reputation": analyze_reputation,
    "analyze_finance": analyze_finance,
    "analyze_procurement": analyze_procurement,
}
