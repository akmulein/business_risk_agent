from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from counterparty_verification.analysis.analyzers import analyze_reputation
from counterparty_verification.analysis.rules.reputation import (
    CHAPTER_LABELS,
    CODE_ALIASES,
    build_view,
)
from counterparty_verification.domain import CounterpartyCard, RiskLevel

RULES_DOC = Path(__file__).parents[2] / "docs" / "rules" / "analyze_reputation.md"

COMPANY_REPORT: dict[str, Any] = {
    "report_id": "r-1",
    "inn": "1684017097",
    "short_name": 'ООО "ТЕСТ"',
    "status": "CURRENT",
}


def _factor(index: int, sign: str, chapter: str, **fields: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "report_id": "r-1",
        "company_inn": "1684017097",
        "sign": sign,
        "item_index": index,
        "code": f"code{index}",
        "name": f"Текст фактора {index}.",
        "chapter": chapter,
    }
    return {**defaults, **fields}


def _card(risk_factors: list[dict[str, Any]]) -> CounterpartyCard:
    return CounterpartyCard.model_validate(
        {"company_reports": COMPANY_REPORT, "risk_factors": risk_factors}
    )


def test_view_groups_by_chapter_in_order_of_appearance() -> None:
    card = _card(
        [
            _factor(0, "negative", "finance"),
            _factor(1, "positive", "reestrs"),
            _factor(2, "negative", "finance"),
        ]
    )

    view = build_view(card)

    assert view.chapters == ["finance", "reestrs"]
    assert [entry.index for entry in view.by_chapter["finance"]] == [0, 2]
    assert [entry.index for entry in view.negative] == [0, 2]
    assert [entry.index for entry in view.positive] == [1]


def test_known_code_typo_is_normalized() -> None:
    card = _card([_factor(0, "positive", "arbitr", code="аrbitrationDefendant")])

    view = build_view(card)

    assert view.indexed[0].code == "arbitrationDefendant"
    assert view.indexed[0].code == CODE_ALIASES["аrbitrationDefendant"]


def test_analyze_reputation_never_assigns_a_verdict() -> None:
    """Fixes the previous bug where any negative factor forced `risk_level=HIGH`."""
    card = _card(
        [
            _factor(0, "negative", "finance"),
            _factor(1, "negative", "reestrs"),
        ]
    )

    result = analyze_reputation(card)

    assert result.risk_level == RiskLevel.UNKNOWN
    assert result.factors == []
    assert result.observations
    assert result.data_sufficient is True


def test_analyze_reputation_reports_insufficient_data() -> None:
    card = _card([])

    result = analyze_reputation(card)

    assert result.risk_level == RiskLevel.UNKNOWN
    assert result.data_sufficient is False
    assert result.observations == []


@pytest.mark.parametrize("chapter", sorted(CHAPTER_LABELS))
def test_every_chapter_is_documented(chapter: str) -> None:
    assert f"`chapter_{chapter}`" in RULES_DOC.read_text(encoding="utf-8")


# -- Added for the tools eval/regression effort: invalidAddress and
# massAddress are independent risk_factor codes (each with its own sign),
# not a boolean pair on one field -- this pins that the tool layer keeps
# both distinct rather than losing or conflating one when they co-occur,
# mirroring the real ООО МАКСМАРКЕТ report (invalidAddress=negative,
# massAddress=positive in the same "reestrs" chapter).


def test_invalid_address_and_mass_address_are_independent_codes() -> None:
    card = _card(
        [
            _factor(
                0,
                "negative",
                "reestrs",
                code="invalidAddress",
                name="Находится в реестре организаций с фиктивным адресом.",
            ),
            _factor(
                1,
                "positive",
                "reestrs",
                code="massAddress",
                name="Не найден в реестре организаций с массовым адресом.",
            ),
        ]
    )

    view = build_view(card)

    assert {entry.code for entry in view.negative} == {"invalidAddress"}
    assert {entry.code for entry in view.positive} == {"massAddress"}

    result = analyze_reputation(card)
    chapter_observation = next(
        item for item in result.observations if item.code == "chapter_reestrs"
    )
    assert "фиктивным адресом" in chapter_observation.detail
    assert "массовым адресом" in chapter_observation.detail
    evidence_values = {item.value for item in chapter_observation.evidence}
    assert "Находится в реестре организаций с фиктивным адресом." in evidence_values
    assert "Не найден в реестре организаций с массовым адресом." in evidence_values


def test_invalid_address_true_does_not_imply_mass_address_true() -> None:
    """A negative invalidAddress entry must not cause massAddress to be
    inferred as negative too when it wasn't reported that way."""
    card = _card(
        [
            _factor(0, "negative", "reestrs", code="invalidAddress"),
            _factor(1, "positive", "reestrs", code="massAddress"),
        ]
    )

    view = build_view(card)
    by_code = {entry.code: entry.item.sign for entry in view.indexed}

    assert by_code["invalidAddress"] == "negative"
    assert by_code["massAddress"] == "positive"
