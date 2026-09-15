from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from counterparty_verification.agents.question_answer import flatten_field_paths
from counterparty_verification.analysis.analyzers import analyze_general
from counterparty_verification.analysis.rules.general import CHECKS
from counterparty_verification.domain import CounterpartyCard, Observation, RiskLevel

RULES_DOC = Path(__file__).parents[2] / "docs" / "rules" / "analyze_general.md"

COMPANY_REPORT: dict[str, Any] = {
    "report_id": "r-1",
    "inn": "1684017097",
    "short_name": 'ООО "ТЕСТ"',
    "status": "CURRENT",
}


def _card(**report: Any) -> CounterpartyCard:
    return CounterpartyCard.model_validate(
        {"company_reports": {**COMPANY_REPORT, **report}}
    )


def _observed(card: CounterpartyCard) -> dict[str, Observation]:
    return {item.code: item for item in analyze_general(card).observations}


def test_chapter_never_grades_the_counterparty() -> None:
    card = _card(status="CLOSED")

    result = analyze_general(card)

    assert result.risk_level == RiskLevel.UNKNOWN
    assert not result.factors
    assert "closed_status" in _observed(card)


def test_closed_status_mentions_reason() -> None:
    card = _card(status="CLOSED", status_reason="Реорганизация")

    detail = _observed(card)["closed_status"].detail

    assert "CLOSED" in detail
    assert "Реорганизация" in detail


def test_current_status_is_silent() -> None:
    card = _card(status="CURRENT")

    assert "closed_status" not in _observed(card)


def test_our_own_assessment_is_never_reported_back_as_an_observation() -> None:
    """The provider of these figures is us, so repeating our own ЗСК and risk
    level tells the reader nothing about the counterparty."""
    card = _card(zsk_risk_level="RED", risk_level="HIGH")

    assert not _observed(card)


def test_quiet_general_card_produces_no_observations() -> None:
    card = _card(status="CURRENT", zsk_risk_level="GREEN", risk_level="LOW")

    result = analyze_general(card)

    assert result.data_sufficient
    assert not result.observations
    assert "не найдено" in result.conclusion


def test_every_evidence_path_exists_in_the_card() -> None:
    card = _card(
        status="CLOSED",
        status_reason="Ликвидация",
        zsk_risk_level="RED",
        risk_level="HIGH",
    )
    allowed = flatten_field_paths(card.model_dump(mode="json"))
    result = analyze_general(card)

    paths = {item.field for item in result.evidence}
    for observation in result.observations:
        paths.update(item.field for item in observation.evidence)

    assert paths
    assert paths <= allowed
    assert "closed_status" in _observed(card)


@pytest.mark.parametrize("check", CHECKS, ids=lambda check: check.code)
def test_every_check_is_documented(check) -> None:
    assert f"`{check.code}`" in RULES_DOC.read_text(encoding="utf-8")


def test_check_codes_are_unique() -> None:
    codes = [check.code for check in CHECKS]

    assert len(codes) == len(set(codes))
    assert len(codes) == 1
