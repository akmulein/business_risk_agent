from pathlib import Path
from typing import Any

import pytest

from counterparty_verification.agents.question_answer import flatten_field_paths
from counterparty_verification.analysis.analyzers import analyze_legal
from counterparty_verification.analysis.rules.legal import CHECKS
from counterparty_verification.domain import CounterpartyCard, Observation, RiskLevel

RULES_DOC = Path(__file__).parents[2] / "docs" / "rules" / "analyze_legal.md"

COMPANY_REPORT: dict[str, Any] = {
    "report_id": "r-1",
    "report_date": "2026-01-01",
    "inn": "1684017097",
    "ogrn": "1241600001048",
    "short_name": 'ООО "ТЕСТ"',
    "full_name": 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ТЕСТ"',
    "status": "CURRENT",
}


def _arb(index: int, **fields: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "id": f"arb-{index}",
        "report_id": "r-1",
        "company_inn": "1684017097",
        "source": "status",
        "role": "defendant",
        "case_status": "pending",
        "case_count": 0,
        "amount": 0,
    }
    return {**defaults, "id": f"arb-{index}", **fields}


def _event(event_type: str, index: int, **fields: Any) -> dict[str, Any]:
    return {
        "report_id": "r-1",
        "company_inn": "1684017097",
        "event_type": event_type,
        "item_index": index,
        **fields,
    }


def _finance(**fields: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "report_id": "r-1",
        "company_inn": "1684017097",
        "year": 2025,
        "proceeds": 10_000_000,
        "profit": 1_000_000,
        "total_assets": 8_000_000,
    }
    return {**defaults, **fields}


def _card(
    *,
    arbitration: list[dict[str, Any]] | None = None,
    legal_events: list[dict[str, Any]] | None = None,
    financial_reports: list[dict[str, Any]] | None = None,
    **report: Any,
) -> CounterpartyCard:
    payload: dict[str, Any] = {
        "company_reports": {**COMPANY_REPORT, **report},
        "arbitration": arbitration or [],
        "legal_events": legal_events or [],
    }
    if financial_reports is not None:
        payload["financial_reports"] = financial_reports
    return CounterpartyCard.model_validate(payload)


def _observed(card: CounterpartyCard) -> dict[str, Observation]:
    return {item.code: item for item in analyze_legal(card).observations}


def test_chapter_never_grades_the_counterparty() -> None:
    card = _card(
        legal_events=[
            _event("execution", 0, active=True, amount=500_000, external_id="1")
        ]
    )

    result = analyze_legal(card)

    assert result.risk_level == RiskLevel.UNKNOWN
    assert not result.factors
    assert "enforcement_load" in _observed(card)


def test_finished_only_defendant_is_silent() -> None:
    card = _card(
        arbitration=[
            _arb(0, case_status="finished", case_count=12, amount=5_000_000),
        ]
    )

    assert "defendant_exposure" not in _observed(card)
    assert analyze_legal(card).data_sufficient


def test_pending_defendant_is_observed_without_yearly_double_count() -> None:
    card = _card(
        arbitration=[
            _arb(
                0,
                source="yearly",
                year=2025,
                role="defendant",
                case_status="all",
                case_count=4,
                amount=4_000_000,
            ),
            _arb(1, case_status="pending", case_count=2, amount=800_000),
            _arb(2, case_status="appealed", case_count=1, amount=200_000),
            _arb(3, case_status="finished", case_count=9, amount=3_000_000),
            _arb(
                4,
                role="plaintiff",
                case_status="pending",
                case_count=5,
                amount=1_500_000,
            ),
        ],
        financial_reports=[_finance(proceeds=20_000_000, profit=500_000)],
    )

    detail = _observed(card)["defendant_exposure"].detail

    assert "открытых 2" in detail
    assert "800 000" in detail
    assert "истец" in detail.lower()
    assert "4 000 000" not in detail
    assert "больше прибыли" in detail


def test_yearly_defendant_alone_does_not_count_as_current_exposure() -> None:
    card = _card(
        arbitration=[
            _arb(
                0,
                source="yearly",
                year=2025,
                role="defendant",
                case_status="all",
                case_count=3,
                amount=9_000_000,
            )
        ]
    )

    assert "defendant_exposure" not in _observed(card)


def test_arbitration_trend_needs_doubling() -> None:
    growing = _card(
        arbitration=[
            _arb(
                0,
                source="yearly",
                year=2024,
                role="defendant",
                case_status="all",
                case_count=2,
                amount=100_000,
            ),
            _arb(
                1,
                source="yearly",
                year=2025,
                role="defendant",
                case_status="all",
                case_count=6,
                amount=400_000,
            ),
        ]
    )
    flat = _card(
        arbitration=[
            _arb(
                0,
                source="yearly",
                year=2024,
                role="defendant",
                case_status="all",
                case_count=4,
                amount=200_000,
            ),
            _arb(
                1,
                source="yearly",
                year=2025,
                role="defendant",
                case_status="all",
                case_count=5,
                amount=220_000,
            ),
        ]
    )

    assert "arbitration_trend" in _observed(growing)
    # Not "в 2 раза" -- that raw-multiplier phrasing was intentionally
    # removed from user-facing text (see commit 079bc7e, "Raw enum values,
    # rule thresholds and ISO dates removed from user-facing texts"); the
    # restored version of this test still asserted the old wording, which
    # is exactly the kind of drift a static interface check can't catch.
    assert "заметно выше" in _observed(growing)["arbitration_trend"].detail
    assert "arbitration_trend" not in _observed(flat)


def test_arbitration_trend_does_not_treat_a_missing_year_as_zero() -> None:
    card = _card(
        arbitration=[
            _arb(
                0,
                source="yearly",
                year=2024,
                role="defendant",
                case_status="all",
                case_count=10,
                amount=100_000,
            ),
            _arb(
                1,
                source="yearly",
                year=2026,
                role="defendant",
                case_status="all",
                case_count=11,
                amount=110_000,
            ),
        ]
    )

    assert "arbitration_trend" not in _observed(card)


def test_three_year_growth_is_observed_without_doubling() -> None:
    card = _card(
        arbitration=[
            _arb(
                index,
                source="yearly",
                year=year,
                role="defendant",
                case_status="all",
                case_count=count,
                amount=count * 10_000,
            )
            for index, (year, count) in enumerate(((2024, 3), (2025, 4), (2026, 5)))
        ]
    )

    assert "три года подряд" in _observed(card)["arbitration_trend"].detail


def test_inactive_execution_is_silent() -> None:
    card = _card(
        legal_events=[
            _event("execution", 0, active=False, amount=9_000_000, external_id="old")
        ]
    )

    assert "enforcement_load" not in _observed(card)
    assert analyze_legal(card).data_sufficient


def test_active_execution_mentions_number_and_scale() -> None:
    card = _card(
        legal_events=[
            _event(
                "execution",
                0,
                active=True,
                amount=800_000,
                external_id="12345/24/77000-ИП",
                event_date="2025-11-01",
            )
        ],
        financial_reports=[_finance(proceeds=10_000_000, profit=100_000)],
    )

    detail = _observed(card)["enforcement_load"].detail

    assert "12345/24/77000-ИП" in detail
    assert "800 000" in detail
    assert "штраф" in detail
    assert "подтверждённый долг" not in detail
    assert "неисполненный долг" not in detail


def test_clean_and_cancelled_inspections_are_silent() -> None:
    card = _card(
        legal_events=[
            _event("inspection", 0, status="завершена без нарушений"),
            _event("inspection", 1, status="отменена"),
            _event("inspection", 2, status="результат неизвестен"),
        ]
    )

    assert "inspection_findings" not in _observed(card)


def test_violations_and_upcoming_inspections_are_observed() -> None:
    card = _card(
        legal_events=[
            _event(
                "inspection",
                0,
                status="завершена с нарушениями",
                authority="ФНС России",
                title="Выездная",
                form="выездная",
                event_date="2025-06-01",
                end_date="2025-06-20",
            ),
            _event(
                "inspection",
                1,
                status="предстоящая",
                authority="Роспотребнадзор",
                event_date="2026-03-01",
            ),
        ]
    )

    detail = _observed(card)["inspection_findings"].detail

    assert "нарушениями" in detail
    assert "предстоящая" in detail
    assert "ФНС" in detail


def test_active_and_indefinite_licenses_are_silent() -> None:
    card = _card(
        legal_events=[
            _event("license", 0, status="ACTIVE", title="Связь"),
            _event("license", 1, status="INDEFINITE", title="Бессрочная"),
        ]
    )

    assert "license_validity" not in _observed(card)


def test_expired_and_expiring_licenses_are_observed() -> None:
    card = _card(
        legal_events=[
            _event(
                "license",
                0,
                status="EXPIRED",
                title="Медицинская",
                external_id="ЛО-77",
                end_date="2025-01-01",
            ),
            _event(
                "license",
                1,
                status="ACTIVE",
                title="Перевозки",
                end_date="2026-03-01",
            ),
        ]
    )

    detail = _observed(card)["license_validity"].detail

    assert "Медицинская" in detail
    assert "Перевозки" in detail
    assert "90 дней" in detail


def test_missing_legal_data_is_insufficient() -> None:
    result = analyze_legal(_card())

    assert not result.data_sufficient
    assert result.risk_level == RiskLevel.UNKNOWN
    assert "Недостаточно" in result.conclusion


def test_quiet_legal_card_produces_no_observations() -> None:
    card = _card(
        arbitration=[
            _arb(0, case_status="finished", case_count=1, amount=10_000),
            _arb(
                1,
                source="yearly",
                year=2025,
                role="defendant",
                case_status="all",
                case_count=1,
                amount=10_000,
            ),
        ],
        legal_events=[
            _event("execution", 0, active=False, amount=1_000),
            _event("inspection", 1, status="завершена без нарушений"),
            _event("license", 2, status="ACTIVE", title="Связь"),
        ],
        financial_reports=[_finance()],
    )

    result = analyze_legal(card)

    assert result.data_sufficient
    assert not result.observations
    assert "не найдено" in result.conclusion


def test_every_evidence_path_exists_in_the_card() -> None:
    card = _card(
        arbitration=[
            _arb(0, case_status="pending", case_count=2, amount=800_000),
            _arb(
                1,
                source="yearly",
                year=2024,
                role="defendant",
                case_status="all",
                case_count=1,
                amount=100_000,
            ),
            _arb(
                2,
                source="yearly",
                year=2025,
                role="defendant",
                case_status="all",
                case_count=4,
                amount=400_000,
            ),
            _arb(
                3,
                source="status",
                role="all",
                case_status="all",
                case_count=10,
                amount=1_000_000,
            ),
        ],
        legal_events=[
            _event("execution", 0, active=True, amount=50_000, external_id="1"),
            _event(
                "inspection",
                1,
                status="завершена с нарушениями",
                authority="ФНС",
            ),
            _event("license", 2, status="EXPIRED", title="Медицина"),
        ],
        financial_reports=[_finance()],
    )
    allowed = flatten_field_paths(card.model_dump(mode="json"))
    result = analyze_legal(card)

    paths = {item.field for item in result.evidence}
    for observation in result.observations:
        paths.update(item.field for item in observation.evidence)

    assert paths
    assert paths <= allowed
    assert {
        "defendant_exposure",
        "arbitration_trend",
        "enforcement_load",
        "inspection_findings",
        "license_validity",
    } <= _observed(card).keys()


@pytest.mark.parametrize("check", CHECKS, ids=lambda check: check.code)
def test_every_check_is_documented(check) -> None:
    assert f"`{check.code}`" in RULES_DOC.read_text(encoding="utf-8")


def test_check_codes_are_unique() -> None:
    codes = [check.code for check in CHECKS]

    assert len(codes) == len(set(codes))
    assert len(codes) == 5


# -- Added for the tools eval/regression effort: edge cases the restored
# suite above didn't exercise (plaintiff/defendant isolation, active
# tri-state, amount=0-vs-missing, and very large -- $numberLong-scale --
# amounts like the real ООО МАКСМАРКЕТ arbitration record).


def test_plaintiff_only_case_never_triggers_defendant_exposure() -> None:
    """A company suing someone else is not the same signal as being sued."""
    card = _card(
        arbitration=[
            _arb(0, role="plaintiff", case_status="pending", case_count=150, amount=5_000_000),
        ]
    )

    assert "defendant_exposure" not in _observed(card)


def test_active_execution_requires_explicit_true_not_just_non_false() -> None:
    """legal.py's tri-state convention: only `active is True` counts.

    Contrast with structure.py's `active_founders`, which treats `is not
    False` (i.e. None counts as active) -- the two modules read the same
    kind of optional bool with opposite defaults. Pinning both conventions
    with explicit tests documents the asymmetry rather than leaving it to
    be rediscovered by accident.
    """
    card = _card(
        legal_events=[
            _event("execution", 0, active=None, amount=9_000_000, external_id="unknown-status"),
        ]
    )

    assert "enforcement_load" not in _observed(card)


def test_present_zero_amount_and_missing_amount_both_stay_silent() -> None:
    card_amount_zero = _card(
        arbitration=[_arb(0, case_status="pending", case_count=0, amount=0)]
    )
    card_amount_missing = _card(
        arbitration=[_arb(0, case_status="pending", case_count=0, amount=None)]
    )

    assert "defendant_exposure" not in _observed(card_amount_zero)
    assert "defendant_exposure" not in _observed(card_amount_missing)


def test_missing_amount_skips_the_scale_clause_that_a_zero_amount_would_not_prevent() -> None:
    """count>0 fires the observation either way, but the *scale* wording
    ("X% от выручки" / "больше прибыли") is only computed when amount is
    genuinely known -- a missing amount must not be silently treated as 0
    for that comparison, since "no data" and "confirmed zero exposure" are
    different claims."""
    card_amount_known = _card(
        arbitration=[_arb(0, case_status="pending", case_count=3, amount=800_000)],
        financial_reports=[_finance(proceeds=10_000_000, profit=100_000)],
    )
    card_amount_missing = _card(
        arbitration=[_arb(0, case_status="pending", case_count=3, amount=None)],
        financial_reports=[_finance(proceeds=10_000_000, profit=100_000)],
    )

    detail_known = _observed(card_amount_known)["defendant_exposure"].detail
    detail_missing = _observed(card_amount_missing)["defendant_exposure"].detail

    assert "%" in detail_known or "больше прибыли" in detail_known
    assert "%" not in detail_missing
    assert "больше прибыли" not in detail_missing


def test_very_large_amount_is_formatted_without_overflow_or_truncation() -> None:
    """Regression guard sized to the real ООО МАКСМАРКЕТ 2024 arbitration
    row: defendantCount=258, defendantAmount=2 589 790 444 -- exercises
    formatting of a number in the same order of magnitude MongoDB would
    represent as $numberLong once normalized into a plain Python float."""
    card = _card(
        arbitration=[
            _arb(0, case_status="pending", case_count=258, amount=2_589_790_444),
        ],
        financial_reports=[_finance(proceeds=1_000_000, profit=10_000)],
    )

    detail = _observed(card)["defendant_exposure"].detail

    assert "2 589 790 444" in detail
    assert "258" in detail
