from counterparty_verification.analysis.comparison import build_comparison
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
