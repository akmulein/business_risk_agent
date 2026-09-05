from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from .domain import (
    ChapterResult,
    CompanyProfile,
    CounterpartyCard,
    CounterpartyPreview,
    FactorSummaryItem,
    FinancialChartPoint,
    LegalChartPoint,
    RiskLevel,
    VisualizationData,
)


FACTOR_LABELS = {
    "reputation": "Критические флаги",
    "legal": "Суды и взыскания",
    "finance": "Финансы",
    "structure": "Руководство",
}

FACTOR_ORDER = tuple(FACTOR_LABELS)

RISK_RANK = {
    RiskLevel.UNKNOWN: 0,
    RiskLevel.LOW: 1,
    RiskLevel.MEDIUM: 2,
    RiskLevel.HIGH: 3,
}

SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[А-ЯA-ZЁ])")
TECHNICAL_REPORT_FIELDS = {
    "_id",
    "report_id",
    "reportId",
    "read_model_version",
}
REPUTATION_TAILS = (
    re.compile(r",\s*это может означать\b", re.IGNORECASE),
    re.compile(r",\s*это может отрицательно\b", re.IGNORECASE),
    re.compile(r",\s*что может указывать\b", re.IGNORECASE),
)


def sanitize_source_report(value: Any) -> Any:
    if isinstance(value, dict):
        if set(value) == {"$date"}:
            return sanitize_source_report(value["$date"])
        if set(value) == {"$numberLong"}:
            raw_number = value["$numberLong"]
            try:
                return int(raw_number)
            except (TypeError, ValueError):
                return raw_number
        return {
            key: sanitize_source_report(item)
            for key, item in value.items()
            if key not in TECHNICAL_REPORT_FIELDS
        }
    if isinstance(value, list):
        return [sanitize_source_report(item) for item in value]
    return value


def build_counterparty_preview(card: CounterpartyCard) -> CounterpartyPreview:
    report = card.company_reports
    return CounterpartyPreview(
        inn=report.inn,
        name=report.short_name or report.full_name or report.inn,
        status=report.status,
        risk_level=report.risk_level,
        kpp=report.kpp,
    )


def build_company_profile(card: CounterpartyCard) -> CompanyProfile:
    report = card.company_reports
    director = next(
        (
            item
            for item in card.structure_items
            if item.item_type == "director" or item.role == "director"
        ),
        None,
    )
    founders_count = sum(
        1
        for item in card.structure_items
        if item.item_type == "founder" and item.active is not False
    )
    return CompanyProfile(
        inn=report.inn,
        kpp=report.kpp,
        ogrn=report.ogrn,
        short_name=report.short_name,
        full_name=report.full_name,
        status=report.status,
        bank_risk_level=report.risk_level,
        director_name=director.name if director else None,
        director_position=director.position if director else None,
        share_capital=report.share_capital,
        staff=report.staff,
        founders_count=founders_count,
        registration_date=report.registration_date,
        address=report.address,
        company_size=report.company_size,
    )


def _unique_details(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        if normalized and normalized not in seen:
            result.append(normalized)
            seen.add(normalized)
    return result


def _sentences(value: str) -> list[str]:
    return [part.strip() for part in SENTENCE_BOUNDARY.split(value.strip()) if part.strip()]


def _with_period(value: str) -> str:
    normalized = value.rstrip(" ,;:")
    return normalized if normalized.endswith((".", "!", "?")) else f"{normalized}."


def _compact_reputation_detail(value: str) -> str:
    sentences = _sentences(value)
    if not sentences:
        return value.strip()

    first = sentences[0]
    cut_positions = [
        match.start()
        for pattern in REPUTATION_TAILS
        if (match := pattern.search(first)) is not None
    ]
    if cut_positions:
        first = first[: min(cut_positions)]
    result = _with_period(first)

    if any(
        "негативно сказывается на репутации и кредитоспособности" in sentence.casefold()
        for sentence in sentences[1:]
    ):
        result += " Это негативно сказывается на репутации и кредитоспособности."
    return result


def _compact_finding_detail(value: str, *, keep_two_sentences: bool = False) -> str:
    sentences = _sentences(value)
    if not sentences:
        return value.strip()
    limit = 2 if keep_two_sentences else 1
    return " ".join(sentences[:limit])


def _chapter_status(chapter: ChapterResult) -> RiskLevel:
    if chapter.factors:
        return max(
            (factor.severity for factor in chapter.factors),
            key=RISK_RANK.get,
        )
    if chapter.observations:
        return RiskLevel.MEDIUM
    if chapter.error or not chapter.data_sufficient:
        return RiskLevel.UNKNOWN
    return RiskLevel.LOW


def build_factor_summary(
    card: CounterpartyCard,
    chapters: list[ChapterResult],
    *,
    compact: bool = True,
) -> list[FactorSummaryItem]:
    chapters_by_name = {chapter.chapter: chapter for chapter in chapters}
    negative_reputation = _unique_details(
        [
            _compact_reputation_detail(item.name) if compact else item.name
            for item in card.risk_factors
            if item.sign == "negative"
        ]
    )
    rows: list[FactorSummaryItem] = []

    for chapter_name in FACTOR_ORDER:
        if chapter_name == "reputation":
            rows.append(
                FactorSummaryItem(
                    chapter=chapter_name,
                    label=FACTOR_LABELS[chapter_name],
                    status=(
                        RiskLevel.HIGH
                        if negative_reputation
                        else RiskLevel.LOW
                    ),
                    details=(
                        negative_reputation
                        or ["Критических факторов в отчёте не указано."]
                    ),
                )
            )
            continue

        chapter = chapters_by_name.get(chapter_name)
        if chapter is None:
            continue
        details = _unique_details(
            [
                _compact_finding_detail(factor.detail) if compact else factor.detail
                for factor in chapter.factors
            ]
            + [
                _compact_finding_detail(
                    observation.detail,
                    keep_two_sentences=observation.code == "okved_breadth",
                )
                if compact
                else observation.detail
                for observation in chapter.observations
            ]
        )
        rows.append(
            FactorSummaryItem(
                chapter=chapter_name,
                label=FACTOR_LABELS[chapter_name],
                status=_chapter_status(chapter),
                details=details or [chapter.conclusion],
            )
        )

    return rows


def _financial_obligations(report: object) -> float | None:
    long_term = getattr(report, "long_term_duties_total", None)
    short_term = getattr(report, "short_term_liabilities_total", None)
    if long_term is not None or short_term is not None:
        return float(long_term or 0) + float(short_term or 0)

    balance_total = getattr(report, "total_liabilities", None)
    capital = getattr(report, "capitals", None)
    if balance_total is not None and capital is not None:
        return float(balance_total) - float(capital)
    return None


def _event_year(value: object) -> int | None:
    if value is None:
        return None
    match = re.match(r"^(\d{4})", str(value))
    return int(match.group(1)) if match else None


def build_visualization_data(card: CounterpartyCard) -> VisualizationData:
    financials = [
        FinancialChartPoint(
            year=item.year,
            revenue=item.proceeds,
            profit=item.profit,
            assets=item.total_assets,
            obligations=_financial_obligations(item),
        )
        for item in sorted(card.financial_reports, key=lambda report: report.year)
    ]

    legal_by_year: dict[int, dict[str, int]] = defaultdict(
        lambda: {"courts": 0, "enforcements": 0}
    )
    for item in card.arbitration:
        if item.source == "yearly" and item.year is not None:
            legal_by_year[item.year]["courts"] += int(item.case_count or 0)

    for item in card.legal_events:
        if item.event_type != "execution":
            continue
        year = _event_year(item.event_date)
        if year is not None:
            legal_by_year[year]["enforcements"] += 1

    years = (
        range(min(legal_by_year), max(legal_by_year) + 1)
        if legal_by_year
        else []
    )
    legal_dynamics = [
        LegalChartPoint(
            year=year,
            courts=legal_by_year[year]["courts"],
            enforcements=legal_by_year[year]["enforcements"],
        )
        for year in years
    ]
    return VisualizationData(
        financials=financials,
        legal_dynamics=legal_dynamics,
    )
