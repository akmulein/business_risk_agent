import pytest

from counterparty_verification.comparison import build_comparison
from counterparty_verification.comparison_agent import (
    CompanyComparisonStatement,
    ComparisonAgent,
    ComparisonStatement,
    ComparisonSummaryOutput,
    _defendant_case_text,
    _enforcement_text,
)
from counterparty_verification.domain import CounterpartyCard, RiskLevel


def _card_with_risk(
    card: CounterpartyCard,
    *,
    inn: str,
    name: str,
    risk_level: RiskLevel,
) -> CounterpartyCard:
    company = card.company_reports.model_copy(
        update={"inn": inn, "short_name": name, "risk_level": risk_level}
    )
    return card.model_copy(update={"company_reports": company}, deep=True)


def test_comparison_preserves_bank_risk_order(card: CounterpartyCard) -> None:
    high = _card_with_risk(
        card, inn="7700000001", name="ООО В", risk_level=RiskLevel.HIGH
    )
    unknown = _card_with_risk(
        card, inn="7700000002", name="ООО Г", risk_level=RiskLevel.UNKNOWN
    )
    low = _card_with_risk(
        card, inn="7700000003", name="ООО А", risk_level=RiskLevel.LOW
    )
    medium = _card_with_risk(
        card, inn="7700000004", name="ООО Б", risk_level=RiskLevel.MEDIUM
    )

    result = build_comparison([high, unknown, low, medium])

    assert [company.risk_level for company in result.companies] == [
        RiskLevel.LOW,
        RiskLevel.MEDIUM,
        RiskLevel.HIGH,
        RiskLevel.UNKNOWN,
    ]
    assert [company.rank for company in result.companies] == [1, 2, 3, 4]


def test_comparison_summary_accepts_only_known_company_facts() -> None:
    facts = {
        "comparison.leaders": {"text": "Лучше выглядит ООО А."},
        "7700000001.profit": {"text": "Прибыль ООО А — 10 ₽."},
        "7700000002.profit": {"text": "Убыток ООО Б — 5 ₽."},
    }
    output = ComparisonSummaryOutput(
        leader_statement=ComparisonStatement(
            text="Лучше выглядит ООО А.", fact_refs=["comparison.leaders"]
        ),
        company_statements=[
            CompanyComparisonStatement(
                company_inn="7700000001",
                text="Прибыль ООО А — 10 ₽.",
                fact_refs=["7700000001.profit"],
            ),
            CompanyComparisonStatement(
                company_inn="7700000002",
                text="Убыток ООО Б — 5 ₽.",
                fact_refs=["7700000002.profit"],
            ),
        ],
    )

    summary = ComparisonAgent._build_summary(output, facts)

    assert summary.startswith("Лучше выглядит ООО А.")
    assert "Убыток ООО Б — 5 ₽." in summary


def test_comparison_summary_rejects_unknown_fact_reference() -> None:
    output = ComparisonSummaryOutput(
        leader_statement=ComparisonStatement(
            text="Лучше выглядит ООО А.", fact_refs=["comparison.leaders"]
        ),
        company_statements=[
            CompanyComparisonStatement(
                company_inn="7700000001",
                text="У ООО А нет замечаний.",
                fact_refs=["7700000001.unknown"],
            ),
            CompanyComparisonStatement(
                company_inn="7700000002",
                text="У ООО Б нет замечаний.",
                fact_refs=["7700000002.unknown"],
            ),
        ],
    )

    with pytest.raises(RuntimeError, match="неизвестные fact_refs"):
        ComparisonAgent._build_summary(
            output,
            {"comparison.leaders": {"text": "Лучше выглядит ООО А."}},
        )


def test_comparison_count_phrases_are_grammatically_correct() -> None:
    assert _enforcement_text(1) == "1 действующее исполнительное производство"
    assert _enforcement_text(2) == "2 действующих исполнительных производства"
    assert _defendant_case_text(5) == "5 текущих арбитражных дел в роли ответчика"
