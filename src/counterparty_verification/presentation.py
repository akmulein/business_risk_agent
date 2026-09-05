from __future__ import annotations

from collections import defaultdict

from .domain import (
    CompanyProfile,
    CounterpartyCard,
    CounterpartyPreview,
    FinancialChartPoint,
    ProcurementChartPoint,
    VisualizationData,
)


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


def build_visualization_data(card: CounterpartyCard) -> VisualizationData:
    financials = [
        FinancialChartPoint(
            year=item.year,
            revenue=item.proceeds,
            profit=item.profit,
            assets=item.total_assets,
            liabilities=item.total_liabilities,
        )
        for item in sorted(card.financial_reports, key=lambda report: report.year)
    ]

    procurements_by_year: dict[int, dict[str, float]] = defaultdict(
        lambda: {
            "admitted": 0,
            "winners": 0,
            "contracts": 0,
            "amount": 0,
        }
    )
    for item in card.procurements:
        aggregate = procurements_by_year[item.year]
        aggregate["admitted"] += int(item.tender_admitted_count or 0)
        aggregate["winners"] += int(item.tender_winner_count or 0)
        aggregate["contracts"] += int(item.contract_signed_count or 0)
        aggregate["amount"] += float(item.contract_signed_amount or 0)

    procurements = [
        ProcurementChartPoint(
            year=year,
            admitted=int(values["admitted"]),
            winners=int(values["winners"]),
            contracts=int(values["contracts"]),
            amount=values["amount"],
        )
        for year, values in sorted(procurements_by_year.items())
    ]
    return VisualizationData(
        financials=financials,
        procurements=procurements,
    )
