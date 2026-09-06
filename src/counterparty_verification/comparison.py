from __future__ import annotations

from .domain import (
    BatchComparison,
    ComparisonCompany,
    CounterpartyCard,
    RiskLevel,
    SourceRiskFactor,
    VerificationStatus,
)

RISK_ORDER = {
    RiskLevel.LOW: 0,
    RiskLevel.MEDIUM: 1,
    RiskLevel.HIGH: 2,
    RiskLevel.UNKNOWN: 3,
}
STATUS_SOURCES = {"status", "by_status"}
FNS_CODES = {
    "taxArrears",
    "taxReporting",
    "fnsBlocking",
    "invalidRegistrationData",
    "invalidAddress",
    "massAddress",
}


def _provider_status(
    factors: list[SourceRiskFactor], codes: set[str]
) -> VerificationStatus:
    matched = [factor for factor in factors if factor.code in codes]
    if any(factor.sign == "negative" for factor in matched):
        return VerificationStatus.ISSUE
    if any(factor.sign == "positive" for factor in matched):
        return VerificationStatus.OK
    return VerificationStatus.NO_DATA


def _defendant_cases(card: CounterpartyCard) -> int | None:
    status_rows = [
        row for row in card.arbitration if row.source in STATUS_SOURCES
    ]
    if not status_rows:
        return None
    return sum(
        row.case_count
        for row in status_rows
        if row.role == "defendant" and row.case_status == "pending"
    )


def _active_enforcements(card: CounterpartyCard) -> int | None:
    executions = [
        event for event in card.legal_events if event.event_type == "execution"
    ]
    if any(event.active is not None for event in executions):
        return sum(event.active is True for event in executions)
    provider_status = _provider_status(card.risk_factors, {"executionProceedings"})
    if provider_status == VerificationStatus.OK:
        return 0
    return None


def _revenue_change(card: CounterpartyCard) -> float | None:
    reports = sorted(
        (report for report in card.financial_reports if report.proceeds is not None),
        key=lambda report: report.year,
    )
    if len(reports) < 2 or reports[-2].proceeds == 0:
        return None
    current = float(reports[-1].proceeds)
    previous = float(reports[-2].proceeds)
    return round((current - previous) / abs(previous) * 100, 1)


def _company_row(card: CounterpartyCard) -> ComparisonCompany:
    report = card.company_reports
    latest_financial = max(
        card.financial_reports,
        key=lambda financial: financial.year,
        default=None,
    )
    return ComparisonCompany(
        rank=0,
        inn=report.inn,
        name=report.short_name or report.full_name or report.inn,
        risk_level=report.risk_level or RiskLevel.UNKNOWN,
        financial_year=latest_financial.year if latest_financial else None,
        revenue=latest_financial.proceeds if latest_financial else None,
        profit=latest_financial.profit if latest_financial else None,
        assets=latest_financial.total_assets if latest_financial else None,
        capital=latest_financial.capitals if latest_financial else None,
        short_term_liabilities=(
            latest_financial.short_term_liabilities_total
            if latest_financial
            else None
        ),
        revenue_change_percent=_revenue_change(card),
        defendant_cases=_defendant_cases(card),
        active_enforcements=_active_enforcements(card),
        fns_status=_provider_status(card.risk_factors, FNS_CODES),
        bankruptcy_status=_provider_status(
            card.risk_factors, {"liquidationStatus"}
        ),
    )


def build_comparison(cards: list[CounterpartyCard]) -> BatchComparison:
    """Build a comparison from report data without calculating a new risk."""

    companies = sorted(
        (_company_row(card) for card in cards),
        key=lambda company: RISK_ORDER[company.risk_level],
    )
    for rank, company in enumerate(companies, start=1):
        company.rank = rank
    return BatchComparison(companies=companies)
