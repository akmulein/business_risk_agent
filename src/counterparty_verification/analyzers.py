from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .domain import ChapterResult, CounterpartyCard, Evidence, RiskFactor, RiskLevel


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
    founders = [
        item for item in card.structure_items if item.item_type == "founder"
    ]
    active_founders = [item for item in founders if item.active is not False]
    managers = [
        item for item in card.structure_items if item.item_type == "director"
    ]
    manager = managers[0] if managers else None
    activities = [
        item for item in card.structure_items if item.item_type == "activity"
    ]
    factors: list[RiskFactor] = []
    if founders and not active_founders:
        factors.append(
            _factor(
                "Нет активных учредителей",
                "Все перечисленные учредители помечены неактивными.",
                RiskLevel.MEDIUM,
                "structure_items.active",
                [item.model_dump(mode="json") for item in founders],
            )
        )
    evidence = [
        Evidence(
            field="structure_items",
            value=[item.model_dump(mode="json") for item in card.structure_items],
        ),
    ]
    sufficient = bool(card.structure_items)
    risk = _risk_max(*(factor.severity for factor in factors), RiskLevel.LOW)
    return ChapterResult(
        chapter="structure",
        risk_level=risk if sufficient else RiskLevel.UNKNOWN,
        conclusion=(
            f"Активных учредителей: {len(active_founders)}; "
            f"руководитель: {manager.name if manager else 'не указан'}; "
            f"видов деятельности: {len(activities)}."
            if sufficient
            else "Недостаточно данных об учредителях и руководстве."
        ),
        factors=factors,
        evidence=evidence,
        data_sufficient=sufficient,
    )


def analyze_legal(card: CounterpartyCard) -> ChapterResult:
    factors: list[RiskFactor] = []
    active_exec = [
        item
        for item in card.legal_events
        if item.event_type == "execution" and item.active is True
    ]
    active_amount = sum(float(item.amount or 0) for item in active_exec)
    if active_exec:
        factors.append(
            _factor(
                "Активные исполнительные производства",
                f"Количество: {len(active_exec)}, сумма: {active_amount:g}.",
                RiskLevel.HIGH,
                "legal_events",
                [item.model_dump(mode="json") for item in active_exec],
            )
        )
    violations = [
        item
        for item in card.legal_events
        if item.event_type == "inspection"
        and "наруш" in str(item.status or "").lower()
    ]
    if violations:
        factors.append(
            _factor(
                "Нарушения по результатам проверок",
                f"Проверок с нарушениями: {len(violations)}.",
                RiskLevel.MEDIUM,
                "legal_events.status",
                [item.model_dump(mode="json") for item in violations],
            )
        )
    expired = [
        item
        for item in card.legal_events
        if item.event_type == "license" and item.status == "EXPIRED"
    ]
    if expired:
        factors.append(
            _factor(
                "Истёкшие лицензии",
                f"Истёкших лицензий: {len(expired)}.",
                RiskLevel.MEDIUM,
                "legal_events.status",
                [item.model_dump(mode="json") for item in expired],
            )
        )
    defendant_amount = sum(
        float(item.amount or 0)
        for item in card.arbitration
        if item.role == "defendant"
    )
    if defendant_amount > 0:
        factors.append(
            _factor(
                "Арбитражные дела в роли ответчика",
                f"Сумма требований по годовым данным: {defendant_amount:g}.",
                RiskLevel.MEDIUM,
                "arbitration",
                [item.model_dump(mode="json") for item in card.arbitration],
            )
        )
    sufficient = bool(card.arbitration or card.legal_events)
    risk = _risk_max(*(factor.severity for factor in factors), RiskLevel.LOW)
    return ChapterResult(
        chapter="legal",
        risk_level=risk if sufficient else RiskLevel.UNKNOWN,
        conclusion=(
            f"Юридических факторов риска найдено: {len(factors)}."
            if sufficient
            else "Недостаточно данных для анализа юридических рисков."
        ),
        factors=factors,
        evidence=[
            Evidence(
                field="arbitration",
                value=[item.model_dump(mode="json") for item in card.arbitration],
            ),
            Evidence(
                field="legal_events",
                value=[item.model_dump(mode="json") for item in card.legal_events],
            ),
        ],
        data_sufficient=sufficient,
    )


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
