from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.analysis.analyzers import (
    analyze_finance,
    analyze_legal,
    analyze_procurement,
    analyze_structure,
)
from app.domain import CounterpartyCard

FIXTURES = json.loads(
    (Path(__file__).parents[1] / "fixtures" / "deterministic_tool_regressions.json").read_text(
        encoding="utf-8"
    )
)


def _card(name: str) -> CounterpartyCard:
    return CounterpartyCard.model_validate(FIXTURES[name]["card"])


def _observations(result: Any) -> dict[str, Any]:
    return {item.code: item for item in result.observations}


def test_finance_g17_albero_does_not_turn_balance_total_into_100_percent_debt() -> None:
    """G17 / 9724033310: assets=capital=10 000 means debt share is 0%, not 100%."""
    result = analyze_finance(_card("finance_albero_g17_9724033310"))
    observations = _observations(result)

    assert "leverage" not in observations
    details = "\n".join(item.detail for item in result.observations)
    assert "100.0%" not in details
    assert "100%" not in details


def test_legal_g08_active_execution_keeps_status_without_confirmed_debt_overclaim() -> None:
    result = analyze_legal(_card("legal_lzso_g08_7805327192"))
    observation = _observations(result)["enforcement_load"]
    detail = observation.detail.lower()

    assert "активных производств: 1" in detail
    assert "800 000" in detail
    assert "12345/24/78004-ип" in detail
    assert "подтверждённый долг" not in detail
    assert "подтвержденный долг" not in detail
    assert "неисполненный долг" not in detail


def test_structure_g21_okved_4321_is_neutral_about_missing_license_or_sro() -> None:
    result = analyze_structure(_card("structure_busov_g21_234803704704"))
    observation = _observations(result)["license_gap"]
    detail = observation.detail.lower()

    assert "43.21" in detail
    assert "провер" in detail
    assert "наличие не подтверждают" in detail
    assert "разрешения нет" not in detail
    assert "лицензии нет" not in detail
    assert "нарушение" not in detail


def test_procurement_g01_winner_gap_is_neutral_and_keeps_223_fz_context() -> None:
    result = analyze_procurement(_card("procurement_le_monlid_g01_5029069967"))
    observation = _observations(result)["contract_signing_gap"]
    detail = observation.detail.lower()

    assert "2024 год — 5" in detail
    assert "2025 год — 1" in detail
    assert "агрегированные счётчики" in detail
    assert "причину расхождения" in detail
    assert "уклон" not in detail
    assert "неподписан" not in detail
    assert "недобросовест" not in detail
    assert "44-фз" not in detail
