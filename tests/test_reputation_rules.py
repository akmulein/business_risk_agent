from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import counterparty_verification.analyzers as analyzers_module
from counterparty_verification.analyzers import analyze_reputation
from counterparty_verification.domain import CounterpartyCard, Observation, RiskLevel
from counterparty_verification.reputation_rules import (
    CHAPTER_LABELS,
    CODE_ALIASES,
    build_view,
)

RULES_DOC = Path(__file__).parents[1] / "tools_rules" / "analyze_reputation.md"

COMPANY_REPORT: dict[str, Any] = {
    "report_id": "r-1",
    "inn": "1684017097",
    "short_name": 'ООО "ТЕСТ"',
    "status": "CURRENT",
}


@pytest.fixture(autouse=True)
def _stub_reputation_agent(monkeypatch: pytest.MonkeyPatch):
    class StubReputationAgent:
        async def aggregate(self, view):
            return [
                Observation(
                    code=f"chapter_{chapter}",
                    title=CHAPTER_LABELS.get(chapter, chapter),
                    detail="; ".join(entry.item.name for entry in entries),
                    evidence=[entry.evidence("name") for entry in entries],
                )
                for chapter, entries in view.by_chapter.items()
            ]

    monkeypatch.setattr(
        analyzers_module,
        "get_reputation_agent",
        lambda: StubReputationAgent(),
    )


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


@pytest.mark.asyncio
async def test_analyze_reputation_never_assigns_a_verdict() -> None:
    """Fixes the previous bug where any negative factor forced `risk_level=HIGH`."""
    card = _card(
        [
            _factor(0, "negative", "finance"),
            _factor(1, "negative", "reestrs"),
        ]
    )

    result = await analyze_reputation(card)

    assert result.risk_level == RiskLevel.UNKNOWN
    assert result.factors == []
    assert result.observations
    assert result.data_sufficient is True


@pytest.mark.asyncio
async def test_analyze_reputation_reports_insufficient_data() -> None:
    card = _card([])

    result = await analyze_reputation(card)

    assert result.risk_level == RiskLevel.UNKNOWN
    assert result.data_sufficient is False
    assert result.observations == []


@pytest.mark.parametrize("chapter", sorted(CHAPTER_LABELS))
def test_every_chapter_is_documented(chapter: str) -> None:
    assert f"`chapter_{chapter}`" in RULES_DOC.read_text(encoding="utf-8")
