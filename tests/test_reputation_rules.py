from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import counterparty_verification.agents as agents_module
from counterparty_verification.agents import flatten_field_paths
from counterparty_verification.analyzers import analyze_reputation
from counterparty_verification.domain import CounterpartyCard, RiskLevel
from counterparty_verification.reputation_rules import (
    CHAPTER_LABELS,
    CODE_ALIASES,
    build_view,
    fallback_observations,
)
from counterparty_verification.settings import Settings

RULES_DOC = Path(__file__).parents[1] / "tools_rules" / "analyze_reputation.md"

COMPANY_REPORT: dict[str, Any] = {
    "report_id": "r-1",
    "inn": "1684017097",
    "short_name": 'ООО "ТЕСТ"',
    "status": "CURRENT",
}


@pytest.fixture(autouse=True)
def _disabled_reputation_agent(monkeypatch: pytest.MonkeyPatch):
    """Forces `ReputationAgent` off, independent of the local environment.

    `get_reputation_agent` is an `lru_cache` singleton reading real
    `Settings` (env / `.env`); without this, an `OPENROUTER_API_KEY` present
    on a developer's machine would make these tests non-deterministic.
    """
    agents_module.get_reputation_agent.cache_clear()
    monkeypatch.setattr(
        agents_module, "get_settings", lambda: Settings(openrouter_api_key=None)
    )
    yield
    agents_module.get_reputation_agent.cache_clear()


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


def test_fallback_observations_use_verbatim_text_and_valid_evidence() -> None:
    card = _card(
        [
            _factor(0, "negative", "finance", name="Убыток за отчётный период."),
            _factor(1, "positive", "finance", name="Стабильная выручка."),
        ]
    )
    view = build_view(card)

    observations = fallback_observations(view)

    assert len(observations) == 1
    observation = observations[0]
    assert observation.code == "chapter_finance"
    assert observation.title == CHAPTER_LABELS["finance"]
    assert "Убыток за отчётный период." in observation.detail
    assert "Стабильная выручка." in observation.detail
    allowed = flatten_field_paths(card.model_dump(mode="json"))
    assert {item.field for item in observation.evidence}.issubset(allowed)


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
