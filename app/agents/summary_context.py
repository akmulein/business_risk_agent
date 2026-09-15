from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.domain import (
    ChapterResult,
    ComparisonCompany,
    RiskLevel,
    VerificationStatus,
)


RISK_LABELS = {
    RiskLevel.LOW: "низкий",
    RiskLevel.MEDIUM: "средний",
    RiskLevel.HIGH: "высокий",
    RiskLevel.UNKNOWN: "не определён",
}
STATUS_LABELS = {
    VerificationStatus.OK: "замечаний нет",
    VerificationStatus.ISSUE: "есть замечания",
    VerificationStatus.NO_DATA: "нет данных",
}
MONEY_METRICS = {
    "revenue": "Выручка",
    "profit": "Чистая прибыль или убыток",
    "assets": "Активы",
    "capital": "Капитал и резервы",
    "short_term_liabilities": "Краткосрочные обязательства",
}
_THOUSAND_RUBLES = re.compile(
    r"(?P<number>\d[\d ]*(?:[.,]\d+)?)\s*"
    r"(?:тыс\.?|тысяч(?:а|и)?)\s*(?:руб(?:\.|ля|лей)?)",
    re.IGNORECASE,
)


class GroundedSummary(BaseModel):
    """Structured model output: prose may use only selected input facts."""

    selected_fact_ids: list[str] = Field(min_length=1)
    summary: str = Field(min_length=1)

    @field_validator("selected_fact_ids")
    @classmethod
    def unique_fact_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("selected_fact_ids must be unique")
        return value


def _decimal(value: float) -> str:
    rendered = f"{value:,.3f}".replace(",", " ").replace(".", ",")
    return rendered.rstrip("0").rstrip(",")


def format_rubles(value: float | int) -> str:
    """Render a ruble amount in its largest familiar order of magnitude."""
    amount = float(value)
    if abs(amount) >= 1_000_000_000:
        return f"{_decimal(amount / 1_000_000_000)} млрд рублей"
    if abs(amount) >= 1_000_000:
        return f"{_decimal(amount / 1_000_000)} млн рублей"
    if abs(amount) >= 1_000:
        return f"{_decimal(amount / 1_000)} тыс. рублей"
    return f"{_decimal(amount)} рублей"


def normalize_money_text(text: str) -> str:
    """Normalize amounts expressed in thousands to a natural larger unit."""

    def replace(match: re.Match[str]) -> str:
        thousands = float(match.group("number").replace(" ", "").replace(",", "."))
        return format_rubles(thousands * 1_000)

    return _THOUSAND_RUBLES.sub(replace, text)


def _fact(
    company_id: str,
    suffix: str,
    topic: str,
    statement: str,
    **attributes: Any,
) -> dict[str, Any]:
    result = {
        "company_id": company_id,
        "fact_id": f"{company_id}.{suffix}",
        "topic": topic,
        "statement": normalize_money_text(statement),
    }
    result.update({key: value for key, value in attributes.items() if value is not None})
    return result


def _core_facts(
    company_id: str,
    company: ComparisonCompany,
) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for field, label in MONEY_METRICS.items():
        value = getattr(company, field)
        if value is None:
            continue
        period = company.financial_year
        period_text = f" за {period} год" if period is not None else ""
        facts.append(
            _fact(
                company_id,
                f"finance.{field}",
                "finance",
                f"{label}{period_text}: {format_rubles(value)}.",
                metric=field,
                value=value,
                unit="RUB",
                period=period,
                display_value=format_rubles(value),
            )
        )
    if company.revenue_change_percent is not None:
        facts.append(
            _fact(
                company_id,
                "finance.revenue_change",
                "finance",
                f"Изменение выручки к предыдущему году: "
                f"{_decimal(company.revenue_change_percent)}%.",
                metric="revenue_change",
                value=company.revenue_change_percent,
                unit="percent",
                period=company.financial_year,
            )
        )
    if company.defendant_cases is not None:
        facts.append(
            _fact(
                company_id,
                "legal.open_defendant_cases",
                "legal",
                "Открытых арбитражных дел в роли ответчика: "
                f"{company.defendant_cases}.",
                metric="defendant_cases",
                value=company.defendant_cases,
                unit="count",
                scope="open",
            )
        )
    if company.active_enforcements is not None:
        facts.append(
            _fact(
                company_id,
                "legal.active_enforcements",
                "legal",
                "Действующих исполнительных производств: "
                f"{company.active_enforcements}.",
                metric="active_enforcements",
                value=company.active_enforcements,
                unit="count",
                scope="active",
            )
        )
    for field, label, scope in (
        (
            "finished_defendant_cases",
            "Завершённых арбитражных дел в роли ответчика",
            "finished",
        ),
        (
            "appealed_defendant_cases",
            "Обжалованных арбитражных дел в роли ответчика",
            "appealed",
        ),
        (
            "total_enforcements",
            "Исполнительных производств всего",
            "all_recorded",
        ),
        (
            "inactive_enforcements",
            "Недействующих или завершённых "
            "исполнительных производств",
            "not_active",
        ),
    ):
        value = getattr(company, field)
        if value is None:
            continue
        facts.append(
            _fact(
                company_id,
                f"legal.{field}",
                "legal",
                f"{label}: {value}.",
                metric=field,
                value=value,
                unit="count",
                scope=scope,
            )
        )
    if company.historical_defendant_cases_present is not None:
        historical = company.historical_defendant_cases_present
        statement = (
            "В исторических данных есть арбитражные дела "
            "в роли ответчика."
            if historical
            else (
                "В исторических данных арбитражные дела "
                "в роли ответчика не найдены."
            )
        )
        facts.append(
            _fact(
                company_id,
                "legal.historical_defendant_cases",
                "legal",
                statement,
                metric="historical_defendant_cases_present",
                value=historical,
                scope="historical",
            )
        )
    facts.append(
        _fact(
            company_id,
            "legal.data_sufficiency",
            "legal",
            (
                "Данных достаточно для перечисления представленных "
                "юридических событий."
                if company.legal_data_sufficient
                else (
                    "Данных недостаточно для вывода о полном "
                    "отсутствии "
                    "юридических рисков."
                )
            ),
            metric="data_sufficient",
            value=company.legal_data_sufficient,
        )
    )
    facts.extend(
        [
            _fact(
                company_id,
                "registry.fns_status",
                "reputation",
                "Статус по реестрам ФНС: "
                f"{STATUS_LABELS[company.fns_status]}.",
                metric="fns_status",
                value=STATUS_LABELS[company.fns_status],
            ),
            _fact(
                company_id,
                "registry.bankruptcy_status",
                "reputation",
                "Статус банкротства: "
                f"{STATUS_LABELS[company.bankruptcy_status]}.",
                metric="bankruptcy_status",
                value=STATUS_LABELS[company.bankruptcy_status],
            ),
        ]
    )
    return facts


def _observation_fact(
    company_id: str,
    chapter_name: str,
    code: str,
    title: str,
    detail: str,
    evidence: list[Any],
) -> dict[str, Any]:
    attributes: list[dict[str, Any]] = []
    money_fields = {
        "proceeds", "profit", "amount", "total_assets", "total_liabilities",
        "capitals", "short_term_liabilities_total", "contract_signed_amount",
    }
    for item in evidence:
        field = item.field.rsplit(".", 1)[-1]
        attribute = {"metric": field, "value": item.value}
        if field in money_fields:
            attribute["unit"] = "RUB"
            if isinstance(item.value, (int, float)):
                attribute["display_value"] = format_rubles(item.value)
        attributes.append(attribute)
    scope = None
    lowered = f"{title} {detail}".lower()
    if chapter_name == "reputation" and "арбитраж" in lowered:
        scope = "historical_or_unspecified"
    elif chapter_name == "reputation" and "исполнительн" in lowered:
        scope = "source_statement; do not interpret as all debts"
    return _fact(
        company_id,
        f"{chapter_name}.observation.{code}",
        chapter_name,
        f"{title}. {detail}",
        attributes=attributes or None,
        scope=scope,
    )


def chapter_context(
    chapters: list[ChapterResult],
    company_id: str,
    company: ComparisonCompany,
) -> list[dict[str, Any]]:
    """Build compact, attributable facts instead of repeated chapter prose."""
    facts = _core_facts(company_id, company)
    seen = {fact["fact_id"] for fact in facts}

    def add(fact: dict[str, Any]) -> None:
        base = fact["fact_id"]
        suffix = 2
        while fact["fact_id"] in seen:
            fact["fact_id"] = f"{base}.{suffix}"
            suffix += 1
        seen.add(fact["fact_id"])
        facts.append(fact)

    for chapter in chapters:
        if not chapter.data_sufficient and chapter.chapter != "legal":
            add(
                _fact(
                    company_id,
                    f"{chapter.chapter}.data_sufficiency",
                    chapter.chapter,
                    chapter.conclusion,
                    metric="data_sufficient",
                    value=False,
                )
            )
        for index, item in enumerate(chapter.observations, start=1):
            if (
                chapter.chapter == "reputation"
                and "исполнительн" in f"{item.title} {item.detail}".lower()
                and company.active_enforcements is not None
            ):
                continue
            details = (
                [part.strip() for part in item.detail.split(";") if part.strip()]
                if chapter.chapter == "reputation"
                else [item.detail]
            )
            for detail_index, detail in enumerate(details, start=1):
                code = item.code or str(index)
                if len(details) > 1:
                    code = f"{code}.{detail_index}"
                evidence = (
                    [item.evidence[detail_index - 1]]
                    if detail_index <= len(item.evidence)
                    else []
                )
                add(
                    _observation_fact(
                        company_id,
                        chapter.chapter,
                        code,
                        item.title,
                        detail,
                        evidence,
                    )
                )
        for index, item in enumerate(chapter.factors, start=1):
            add(
                _fact(
                    company_id,
                    f"{chapter.chapter}.factor.{index}",
                    chapter.chapter,
                    f"{item.title}. {item.detail}",
                    severity=RISK_LABELS[item.severity],
                )
            )
        if (
            chapter.data_sufficient
            and not chapter.observations
            and not chapter.factors
            and chapter.chapter in {"general", "procurement"}
        ):
            add(
                _fact(
                    company_id,
                    f"{chapter.chapter}.summary",
                    chapter.chapter,
                    chapter.conclusion,
                )
            )
    return facts


def validate_selected_facts(
    output: GroundedSummary,
    facts: list[dict[str, Any]],
    expected_company_ids: set[str] | None = None,
) -> None:
    available = {fact["fact_id"] for fact in facts}
    unknown = sorted(set(output.selected_fact_ids) - available)
    if unknown:
        raise RuntimeError(f"Summary selected unknown fact ids: {', '.join(unknown)}")
    if expected_company_ids:
        selected_companies = {
            fact["company_id"]
            for fact in facts
            if fact["fact_id"] in output.selected_fact_ids
        }
        missing = sorted(expected_company_ids - selected_companies)
        if missing:
            raise RuntimeError(
                "Comparison omitted companies: " + ", ".join(missing)
            )
