from __future__ import annotations

from typing import Any

import pytest

from app.analysis.analyzers import (
    analyze_finance,
    analyze_general,
    analyze_legal,
    analyze_procurement,
    analyze_reputation,
    analyze_structure,
)
from app.domain import CounterpartyCard, RiskLevel


BASE_REPORT: dict[str, Any] = {
    "report_id": "contract-r-1",
    "inn": "7700000000",
    "short_name": 'ООО "КОНТРАКТ"',
    "full_name": 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "КОНТРАКТ"',
    "status": "CURRENT",
    "risk_level": "LOW",
    "zsk_risk_level": "GREEN",
}


def _card(**payload: Any) -> CounterpartyCard:
    report = {**BASE_REPORT, **payload.pop("company_reports", {})}
    return CounterpartyCard.model_validate({"company_reports": report, **payload})


def _factor(index: int, sign: str, chapter: str, code: str, name: str) -> dict[str, Any]:
    return {
        "report_id": "contract-r-1",
        "company_inn": "7700000000",
        "item_index": index,
        "sign": sign,
        "chapter": chapter,
        "code": code,
        "name": name,
    }


def test_all_six_production_tools_are_directly_callable_without_llm() -> None:
    card = _card()

    results = {
        "general": analyze_general(card),
        "finance": analyze_finance(card),
        "legal": analyze_legal(card),
        "procurement": analyze_procurement(card),
        "reputation": analyze_reputation(card),
        "structure": analyze_structure(card),
    }

    assert set(results) == {
        "general",
        "finance",
        "legal",
        "procurement",
        "reputation",
        "structure",
    }
    assert all(result.risk_level is RiskLevel.UNKNOWN for result in results.values())


def test_general_preserves_identity_status_and_does_not_echo_provider_risk_as_verdict() -> None:
    card = _card()

    result = analyze_general(card)

    evidence = {item.field: item.value for item in result.evidence}
    assert evidence["company_reports.inn"] == "7700000000"
    assert evidence["company_reports.full_name"] == BASE_REPORT["full_name"]
    assert evidence["company_reports.status"] == "CURRENT"
    assert result.risk_level is RiskLevel.UNKNOWN
    assert result.observations == []
    assert "LOW" not in result.conclusion
    assert "GREEN" not in result.conclusion


def test_general_missing_status_stays_unknown_not_zero_or_closed() -> None:
    card = _card(company_reports={"status": None})

    result = analyze_general(card)

    assert result.risk_level is RiskLevel.UNKNOWN
    assert result.observations == []
    assert "не указан" in result.conclusion
    assert "0" not in result.conclusion
    assert "закрыт" not in result.conclusion.lower()


def test_reputation_preserves_positive_negative_chapter_and_raw_meaning() -> None:
    card = _card(
        risk_factors=[
            _factor(
                0,
                "negative",
                "reestrs",
                "invalidAddress",
                "Находится в реестре организаций с фиктивным адресом.",
            ),
            _factor(
                1,
                "positive",
                "reestrs",
                "massAddress",
                "Не найден в реестре организаций с массовым адресом.",
            ),
        ]
    )

    result = analyze_reputation(card)

    assert result.risk_level is RiskLevel.UNKNOWN
    assert len(result.observations) == 1
    observation = result.observations[0]
    assert observation.code == "chapter_reestrs"
    assert "фиктивным адресом" in observation.detail
    assert "массовым адресом" in observation.detail
    evidence = {item.field: item.value for item in observation.evidence}
    assert evidence["risk_factors[0].name"] == "Находится в реестре организаций с фиктивным адресом."
    assert evidence["risk_factors[1].name"] == "Не найден в реестре организаций с массовым адресом."


def test_reputation_missing_factors_are_insufficient_not_absence_of_risk() -> None:
    result = analyze_reputation(_card(risk_factors=[]))

    assert result.risk_level is RiskLevel.UNKNOWN
    assert result.data_sufficient is False
    assert result.observations == []
    assert "нет риска" not in result.conclusion.lower()
    assert "0" not in result.conclusion
