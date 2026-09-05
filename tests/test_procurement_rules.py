from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from counterparty_verification.agents import flatten_field_paths
from counterparty_verification.analyzers import analyze_procurement
from counterparty_verification.domain import CounterpartyCard, Observation, RiskLevel
from counterparty_verification.procurement_rules import CHECKS

RULES_DOC = Path(__file__).parents[1] / "tools_rules" / "analyze_procurement.md"

COMPANY_REPORT: dict[str, Any] = {
    "report_id": "r-1",
    "inn": "1684017097",
    "short_name": 'ООО "ТЕСТ"',
    "status": "CURRENT",
    "report_date": "2026-01-15",
}


def _procurement(**fields: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "report_id": "r-1",
        "company_inn": "1684017097",
        "item_index": 0,
        "year": 2025,
    }
    return {**defaults, **fields}


def _card(
    *,
    procurements: list[dict[str, Any]] | None = None,
    **report: Any,
) -> CounterpartyCard:
    payload: dict[str, Any] = {"company_reports": {**COMPANY_REPORT, **report}}
    if procurements is not None:
        for index, item in enumerate(procurements):
            item.setdefault("item_index", index)
        payload["procurements"] = procurements
    return CounterpartyCard.model_validate(payload)


def _observed(card: CounterpartyCard) -> dict[str, Observation]:
    return {item.code: item for item in analyze_procurement(card).observations}


def test_chapter_never_grades_the_counterparty() -> None:
    card = _card(
        procurements=[_procurement(tender_admitted_count=10, tender_winner_count=1)]
    )

    result = analyze_procurement(card)

    assert result.risk_level == RiskLevel.UNKNOWN
    assert not result.factors


def test_missing_procurement_data_is_insufficient() -> None:
    result = analyze_procurement(_card())

    assert not result.data_sufficient
    assert result.risk_level == RiskLevel.UNKNOWN
    assert "отсутствуют" in result.conclusion


def test_quiet_procurement_card_produces_no_observations() -> None:
    card = _card(
        procurements=[
            _procurement(
                tender_admitted_count=10,
                tender_winner_count=6,
                contract_signed_count=6,
                contract_signed_amount=5_000_000,
                federal_law_code="44-ФЗ",
            )
        ]
    )

    result = analyze_procurement(card)

    assert result.data_sufficient
    assert not result.observations
    assert "не найдено" in result.conclusion


def test_low_win_rate_is_observed() -> None:
    card = _card(
        procurements=[_procurement(tender_admitted_count=20, tender_winner_count=1)]
    )

    detail = _observed(card)["abnormal_win_rate"].detail

    assert "5.0%" in detail
    assert "конкурентоспособности" in detail


def test_high_win_rate_is_observed() -> None:
    card = _card(
        procurements=[_procurement(tender_admitted_count=10, tender_winner_count=10)]
    )

    detail = _observed(card)["abnormal_win_rate"].detail

    assert "100.0%" in detail
    assert "согласованности" in detail


def test_moderate_win_rate_is_silent() -> None:
    card = _card(
        procurements=[_procurement(tender_admitted_count=10, tender_winner_count=5)]
    )

    assert "abnormal_win_rate" not in _observed(card)


def test_win_rate_is_silent_below_significance_threshold() -> None:
    card = _card(
        procurements=[_procurement(tender_admitted_count=2, tender_winner_count=2)]
    )

    assert "abnormal_win_rate" not in _observed(card)


def test_contract_signing_gap_is_observed() -> None:
    card = _card(
        procurements=[
            _procurement(tender_winner_count=5, contract_signed_count=3, year=2024)
        ]
    )

    detail = _observed(card)["contract_signing_gap"].detail

    assert "2024" in detail
    assert "недостаёт 2" in detail
    assert "недобросовестных поставщиков" in detail


def test_all_wins_signed_is_silent() -> None:
    card = _card(
        procurements=[_procurement(tender_winner_count=5, contract_signed_count=5)]
    )

    assert "contract_signing_gap" not in _observed(card)


def test_activity_dropoff_is_observed_after_two_silent_years() -> None:
    card = _card(
        report_date="2026-06-01",
        procurements=[
            _procurement(year=2022, tender_winner_count=3, contract_signed_count=3),
            _procurement(year=2023, tender_winner_count=2, contract_signed_count=2),
        ],
    )

    detail = _observed(card)["activity_dropoff"].detail

    assert "2023" in detail
    assert "аккредитации" in detail


def test_recent_activity_keeps_dropoff_silent() -> None:
    card = _card(
        report_date="2026-06-01",
        procurements=[
            _procurement(year=2024, tender_winner_count=3, contract_signed_count=3),
            _procurement(year=2025, tender_winner_count=2, contract_signed_count=2),
        ],
    )

    assert "activity_dropoff" not in _observed(card)


def test_single_year_without_wins_has_no_dropoff() -> None:
    card = _card(
        report_date="2026-06-01",
        procurements=[_procurement(year=2020, tender_admitted_count=1)],
    )

    assert "activity_dropoff" not in _observed(card)


def test_single_old_year_with_a_win_is_a_dropoff() -> None:
    card = _card(
        report_date="2026-06-01",
        procurements=[
            _procurement(year=2015, tender_winner_count=1, contract_signed_count=1)
        ],
    )

    assert "activity_dropoff" in _observed(card)


def test_contract_size_spike_is_observed() -> None:
    card = _card(
        procurements=[
            _procurement(
                year=2023, contract_signed_count=5, contract_signed_amount=1_000_000
            ),
            _procurement(
                year=2024, contract_signed_count=5, contract_signed_amount=1_200_000
            ),
            _procurement(
                year=2025, contract_signed_count=1, contract_signed_amount=20_000_000
            ),
        ]
    )

    detail = _observed(card)["contract_size_spike"].detail

    assert "2025" in detail
    assert "раза больше" in detail


def test_proportional_contract_growth_is_silent() -> None:
    card = _card(
        procurements=[
            _procurement(
                year=2024, contract_signed_count=5, contract_signed_amount=1_000_000
            ),
            _procurement(
                year=2025, contract_signed_count=5, contract_signed_amount=1_500_000
            ),
        ]
    )

    assert "contract_size_spike" not in _observed(card)


def test_law_regime_mix_is_observed() -> None:
    card = _card(
        procurements=[
            _procurement(
                federal_law_code="223-ФЗ",
                contract_signed_count=4,
                contract_signed_amount=9_000_000,
            ),
            _procurement(
                item_index=1,
                federal_law_code="44-ФЗ",
                contract_signed_count=1,
                contract_signed_amount=1_000_000,
            ),
        ]
    )

    detail = _observed(card)["law_regime_mix"].detail

    assert "90.0%" in detail
    assert "223-ФЗ" in detail


def test_balanced_law_mix_is_silent() -> None:
    card = _card(
        procurements=[
            _procurement(
                federal_law_code="223-ФЗ",
                contract_signed_count=2,
                contract_signed_amount=2_000_000,
            ),
            _procurement(
                item_index=1,
                federal_law_code="44-ФЗ",
                contract_signed_count=2,
                contract_signed_amount=2_000_000,
            ),
        ]
    )

    assert "law_regime_mix" not in _observed(card)


def test_law_mix_is_silent_below_significance_threshold() -> None:
    card = _card(
        procurements=[
            _procurement(
                federal_law_code="223-ФЗ",
                contract_signed_count=1,
                contract_signed_amount=1_000_000,
            )
        ]
    )

    assert "law_regime_mix" not in _observed(card)


def test_every_evidence_path_exists_in_the_card() -> None:
    card = _card(
        report_date="2026-06-01",
        procurements=[
            _procurement(
                year=2022,
                federal_law_code="223-ФЗ",
                tender_admitted_count=20,
                tender_winner_count=1,
                contract_signed_count=1,
                contract_signed_amount=1_000_000,
            ),
            _procurement(
                item_index=1,
                year=2023,
                federal_law_code="223-ФЗ",
                tender_admitted_count=5,
                tender_winner_count=4,
                contract_signed_count=2,
                contract_signed_amount=1_500_000,
            ),
        ],
    )
    allowed = flatten_field_paths(card.model_dump(mode="json"))
    result = analyze_procurement(card)

    paths = {item.field for item in result.evidence}
    for observation in result.observations:
        paths.update(item.field for item in observation.evidence)

    assert paths
    assert paths <= allowed


@pytest.mark.parametrize("check", CHECKS, ids=lambda check: check.code)
def test_every_check_is_documented(check) -> None:
    assert f"`{check.code}`" in RULES_DOC.read_text(encoding="utf-8")


def test_check_codes_are_unique() -> None:
    codes = [check.code for check in CHECKS]

    assert len(codes) == len(set(codes))
    assert len(codes) == 5
