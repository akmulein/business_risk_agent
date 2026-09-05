from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from counterparty_verification.agents import flatten_field_paths
from counterparty_verification.analyzers import analyze_finance
from counterparty_verification.domain import CounterpartyCard, Observation, RiskLevel
from counterparty_verification.finance_rules import CHECKS

RULES_DOC = Path(__file__).parents[1] / "tools_rules" / "analyze_finance.md"

COMPANY_REPORT: dict[str, Any] = {
    "report_id": "r-1",
    "inn": "1684017097",
    "short_name": 'ООО "ТЕСТ"',
    "status": "CURRENT",
}


def _finance(**fields: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "report_id": "r-1",
        "company_inn": "1684017097",
        "year": 2025,
    }
    return {**defaults, **fields}


def _card(
    *,
    financial_reports: list[dict[str, Any]] | None = None,
    **report: Any,
) -> CounterpartyCard:
    payload: dict[str, Any] = {"company_reports": {**COMPANY_REPORT, **report}}
    if financial_reports is not None:
        payload["financial_reports"] = financial_reports
    return CounterpartyCard.model_validate(payload)


def _observed(card: CounterpartyCard) -> dict[str, Observation]:
    return {item.code: item for item in analyze_finance(card).observations}


HEALTHY_REPORT = _finance(
    year=2025,
    proceeds=12_000_000,
    profit=1_500_000,
    total_assets=10_000_000,
    current_assets_total=6_000_000,
    short_term_liabilities_total=3_000_000,
    total_liabilities=4_000_000,
    capitals=6_000_000,
    sustainability=0.7,
    solvency=2.0,
)


def test_chapter_never_grades_the_counterparty() -> None:
    card = _card(financial_reports=[_finance(profit=-100_000)])

    result = analyze_finance(card)

    assert result.risk_level == RiskLevel.UNKNOWN
    assert not result.factors
    assert "net_loss" in _observed(card)


def test_loss_is_observed_with_amount() -> None:
    card = _card(financial_reports=[_finance(year=2025, profit=-2_000_000)])

    detail = _observed(card)["net_loss"].detail

    assert "2 000 000" in detail
    assert "2025" in detail


def test_positive_profit_is_silent() -> None:
    card = _card(financial_reports=[_finance(profit=500_000)])

    assert "net_loss" not in _observed(card)


def test_single_year_revenue_drop_is_observed() -> None:
    card = _card(
        financial_reports=[
            _finance(year=2024, proceeds=12_000_000),
            _finance(year=2025, proceeds=10_000_000),
        ]
    )

    detail = _observed(card)["revenue_decline"].detail

    assert "12 000 000" in detail
    assert "10 000 000" in detail
    assert "-16.7%" in detail
    assert "второй год подряд" not in detail


def test_two_year_revenue_decline_is_flagged_as_running() -> None:
    card = _card(
        financial_reports=[
            _finance(year=2023, proceeds=12_000_000),
            _finance(year=2024, proceeds=11_000_000),
            _finance(year=2025, proceeds=9_000_000),
        ]
    )

    detail = _observed(card)["revenue_decline"].detail

    assert "второй год подряд" in detail
    assert "2023" in detail and "2024" in detail and "2025" in detail


def test_revenue_growth_is_silent() -> None:
    card = _card(
        financial_reports=[
            _finance(year=2024, proceeds=10_000_000),
            _finance(year=2025, proceeds=12_000_000),
        ]
    )

    assert "revenue_decline" not in _observed(card)


def test_single_report_has_no_revenue_trend() -> None:
    card = _card(financial_reports=[_finance(proceeds=10_000_000)])

    assert "revenue_decline" not in _observed(card)


def test_liquidity_gap_from_provider_solvency() -> None:
    card = _card(financial_reports=[_finance(solvency=0.8)])

    detail = _observed(card)["liquidity_gap"].detail

    assert "0.80" in detail
    assert "Коэффициент платёжеспособности" in detail


def test_liquidity_gap_falls_back_to_computed_ratio_without_solvency() -> None:
    card = _card(
        financial_reports=[
            _finance(current_assets_total=800_000, short_term_liabilities_total=1_000_000)
        ]
    )

    detail = _observed(card)["liquidity_gap"].detail

    assert "0.80" in detail
    assert "расчёте" not in detail  # источник называется явно, а не общим словом
    assert "Отношение оборотных активов" in detail


def test_liquidity_at_or_above_threshold_is_silent() -> None:
    card = _card(financial_reports=[_finance(solvency=1.5)])

    assert "liquidity_gap" not in _observed(card)


def test_negative_equity_is_observed_with_scale() -> None:
    card = _card(
        financial_reports=[
            _finance(capitals=-500_000, total_liabilities=2_000_000, total_assets=1_500_000)
        ]
    )

    detail = _observed(card)["negative_equity"].detail

    assert "-500 000" in detail
    assert "2 000 000" in detail
    assert "1 500 000" in detail


def test_positive_equity_is_silent() -> None:
    card = _card(financial_reports=[_finance(capitals=100_000)])

    assert "negative_equity" not in _observed(card)


def test_leverage_from_provider_sustainability() -> None:
    card = _card(financial_reports=[_finance(sustainability=0.3)])

    detail = _observed(card)["leverage"].detail

    assert "0.30" in detail
    assert "финансовой устойчивости" in detail


def test_leverage_falls_back_to_computed_debt_share_without_sustainability() -> None:
    card = _card(
        financial_reports=[_finance(total_liabilities=900_000, total_assets=1_000_000)]
    )

    detail = _observed(card)["leverage"].detail

    assert "90.0%" in detail
    assert "не указан" in detail


def test_healthy_sustainability_is_silent() -> None:
    card = _card(financial_reports=[_finance(sustainability=0.7)])

    assert "leverage" not in _observed(card)


def test_missing_financial_data_is_insufficient() -> None:
    result = analyze_finance(_card())

    assert not result.data_sufficient
    assert result.risk_level == RiskLevel.UNKNOWN
    assert "отсутствуют" in result.conclusion


def test_quiet_finance_card_produces_no_observations() -> None:
    card = _card(financial_reports=[HEALTHY_REPORT])

    result = analyze_finance(card)

    assert result.data_sufficient
    assert not result.observations
    assert "не найдено" in result.conclusion


def test_every_evidence_path_exists_in_the_card() -> None:
    card = _card(
        financial_reports=[
            _finance(
                year=2024,
                proceeds=12_000_000,
                profit=-1_000_000,
                capitals=-200_000,
                total_liabilities=2_000_000,
                total_assets=1_800_000,
                solvency=0.7,
                sustainability=0.3,
            ),
            _finance(
                year=2025,
                proceeds=10_000_000,
                profit=-500_000,
                capitals=-300_000,
                total_liabilities=2_100_000,
                total_assets=1_700_000,
                solvency=0.6,
                sustainability=0.2,
            ),
        ]
    )
    allowed = flatten_field_paths(card.model_dump(mode="json"))
    result = analyze_finance(card)

    paths = {item.field for item in result.evidence}
    for observation in result.observations:
        paths.update(item.field for item in observation.evidence)

    assert paths
    assert paths <= allowed
    assert {"net_loss", "revenue_decline", "liquidity_gap", "negative_equity", "leverage"} <= _observed(
        card
    ).keys()


@pytest.mark.parametrize("check", CHECKS, ids=lambda check: check.code)
def test_every_check_is_documented(check) -> None:
    assert f"`{check.code}`" in RULES_DOC.read_text(encoding="utf-8")


def test_check_codes_are_unique() -> None:
    codes = [check.code for check in CHECKS]

    assert len(codes) == len(set(codes))
    assert len(codes) == 5
