import pytest
from pydantic import ValidationError

from counterparty_verification.analyzers import ANALYZERS
from counterparty_verification.domain import (
    AnalysisRequest,
    CounterpartyCard,
    LegalEvent,
    RiskLevel,
)


def test_validates_legal_entity_inn() -> None:
    assert AnalysisRequest(inns=["7707083893"]).inns == ["7707083893"]
    with pytest.raises(ValidationError):
        AnalysisRequest(inns=["7707083894"])
    with pytest.raises(ValidationError):
        AnalysisRequest(inns=["123"])


def test_validates_individual_entrepreneur_inn() -> None:
    assert AnalysisRequest(inns=["772377037026"]).inns == ["772377037026"]
    with pytest.raises(ValidationError):
        AnalysisRequest(inns=["772377037027"])


def test_batch_accepts_at_most_ten_inns() -> None:
    request = AnalysisRequest(
        inns=["7707083893", "772377037026"]
    )
    assert request.inns == ["7707083893", "772377037026"]

    with pytest.raises(ValidationError):
        AnalysisRequest(inns=[])
    with pytest.raises(ValidationError):
        AnalysisRequest(inns=["7707083893"] * 11)


@pytest.mark.parametrize("tool_name", ANALYZERS)
def test_every_chapter_returns_grounded_result(
    tool_name: str, card: CounterpartyCard
) -> None:
    result = ANALYZERS[tool_name](card)

    assert result.chapter
    assert result.conclusion
    assert result.risk_level in RiskLevel
    for factor in result.factors:
        assert factor.evidence
        assert all(evidence.field for evidence in factor.evidence)


def test_legal_analyzer_detects_active_enforcement(
    card: CounterpartyCard,
) -> None:
    card.legal_events.append(
        LegalEvent(
            report_id=card.company_reports.report_id,
            company_inn=card.company_reports.inn,
            event_type="execution",
            item_index=0,
            external_id="1",
            active=True,
            amount=500_000,
        )
    )

    result = ANALYZERS["analyze_legal"](card)

    assert result.risk_level == RiskLevel.HIGH
    assert any("исполнительные" in item.title.lower() for item in result.factors)
