"""Level 2: report -> 6 tools -> aggregated context.

One rich card that carries data for every chapter at once, run through all
six `ANALYZERS`. The concern this guards against is specific to a
multi-tool pipeline and can't be caught by testing each rule module in
isolation: a chapter reading (or leaking evidence from) another chapter's
section of the card. Each module's actual field-read set below is taken
directly from the current source of analysis/rules/*.py (confirmed no
module reads outside it), not guessed.
"""

from __future__ import annotations

import inspect

from counterparty_verification.analysis.analyzers import ANALYZERS
from counterparty_verification.analysis.service import TOOL_NAMES
from counterparty_verification.domain import CounterpartyCard
from counterparty_verification.mcp.client import LocalAnalysisToolClient

# The one legitimate cross-chapter overlap: some risk_factors codes
# (invalidRegistrationData, disqualifiedAuthpersons, invalidAuthpersonsData,
# massAuthpersons) are read by both "structure" (rules/structure.py's
# provider_flags) and "reputation" (which groups *all* risk_factors) --
# documented in docs/rules/analyze_reputation.md. Everything else below is
# expected to be chapter-exclusive.
ALLOWED_EVIDENCE_PREFIXES: dict[str, set[str]] = {
    "general": {"company_reports"},
    "structure": {"structure_items", "risk_factors", "legal_events", "company_reports"},
    "legal": {"arbitration", "legal_events", "financial_reports", "company_reports"},
    "reputation": {"risk_factors"},
    "finance": {"financial_reports"},
    "procurement": {"procurements", "company_reports"},
}


def _rich_card() -> CounterpartyCard:
    identity = {"report_id": "r-1", "company_inn": "1684017097"}
    return CounterpartyCard.model_validate(
        {
            "company_reports": {
                "report_id": "r-1",
                "inn": "1684017097",
                "short_name": 'ООО "ИНТЕГРАЦИЯ"',
                "status": "CURRENT",
                "report_date": "2026-01-15",
                "share_capital": 10_000,
            },
            "structure_items": [
                {
                    **identity,
                    "id": "director-0",
                    "item_type": "director",
                    "item_index": 0,
                    "name": "ИВАНОВ ИВАН ИВАНОВИЧ",
                    "related_inn": "130801590508",
                    "position": "ГЕНЕРАЛЬНЫЙ ДИРЕКТОР",
                    "date_from": "2020-01-01",
                },
                {
                    **identity,
                    "id": "founder-0",
                    "item_type": "founder",
                    "item_index": 1,
                    "name": "ИВАНОВ ИВАН ИВАНОВИЧ",
                    "related_inn": "130801590508",
                    "role": "founder",
                    "share": 100,
                    "amount": 10_000,
                    "active": True,
                },
            ],
            "financial_reports": [
                # `profit` is deliberately NOT the fingerprint here: legal.py
                # legitimately reads financial_reports.profit too (the
                # defendant/enforcement "scale" comparison text), so a
                # profit-based fingerprint would show up under both finance
                # and legal by design, not by leakage. `capitals` is finance
                # -exclusive (legal.py never reads it) -- see
                # ALLOWED_EVIDENCE_PREFIXES and the docs/rules research this
                # suite is built from.
                {**identity, "year": 2025, "proceeds": 5_000_000, "profit": -50_000, "capitals": -333_333},
            ],
            "risk_factors": [
                {
                    **identity,
                    "sign": "negative",
                    "item_index": 0,
                    "code": "fnsBlocking",
                    "name": "Есть блокировки банковских счетов по постановлениям налоговой.",
                    "chapter": "reestrs",
                },
            ],
            "arbitration": [
                {
                    **identity,
                    "id": "arb-0",
                    "source": "status",
                    "role": "defendant",
                    "case_status": "pending",
                    "case_count": 2,
                    "amount": 777_777,
                },
                {
                    **identity,
                    "id": "arb-1",
                    "source": "status",
                    "role": "plaintiff",
                    "case_status": "pending",
                    "case_count": 1,
                    "amount": 50_000,
                },
            ],
            "legal_events": [
                {
                    **identity,
                    "event_type": "execution",
                    "item_index": 0,
                    "active": True,
                    "amount": 111_111,
                    "external_id": "999/24/00000-ИП",
                },
            ],
            "procurements": [
                {
                    **identity,
                    "item_index": 0,
                    "year": 2025,
                    "federal_law_code": "44-ФЗ",
                    "tender_admitted_count": 10,
                    "tender_winner_count": 1,
                    "contract_signed_count": 1,
                    "contract_signed_amount": 222_222,
                },
            ],
        }
    )


def _all_evidence_values(result) -> set:
    values = {item.value for item in result.evidence}
    for observation in result.observations:
        values.update(item.value for item in observation.evidence)
    for factor in result.factors:
        values.update(item.value for item in factor.evidence)
    return values


def _all_evidence_prefixes(result) -> set[str]:
    fields = {item.field for item in result.evidence}
    for observation in result.observations:
        fields.update(item.field for item in observation.evidence)
    for factor in result.factors:
        fields.update(item.field for item in factor.evidence)
    return {field.split(".")[0].split("[")[0] for field in fields}


async def _run_all(card: CounterpartyCard) -> dict[str, object]:
    client = LocalAnalysisToolClient()
    results = {}
    for tool_name in TOOL_NAMES:
        result = await client.call(tool_name, card)
        results[result.chapter] = result
    return results


async def test_tool_names_match_the_analyzer_registry() -> None:
    assert set(TOOL_NAMES) == set(ANALYZERS)
    assert len(TOOL_NAMES) == 6


async def test_every_chapter_only_cites_its_own_section_of_the_card() -> None:
    """No tool's evidence leaks a field path from another section."""
    card = _rich_card()
    results = await _run_all(card)

    assert set(results) == {
        "general",
        "structure",
        "legal",
        "reputation",
        "finance",
        "procurement",
    }
    for chapter, result in results.items():
        prefixes = _all_evidence_prefixes(result)
        allowed = ALLOWED_EVIDENCE_PREFIXES[chapter]
        assert prefixes <= allowed, (
            f"{chapter} chapter cited evidence outside its section: "
            f"{prefixes - allowed}"
        )


async def test_no_chapter_is_silently_dropped_for_a_fully_populated_card() -> None:
    """Every section of the rich card has a signal that should fire an
    observation somewhere -- if a chapter comes back empty, either its tool
    silently ignored real input, or the card fixture stopped matching the
    rule it's meant to exercise."""
    card = _rich_card()
    results = await _run_all(card)

    for chapter, result in results.items():
        assert result.data_sufficient, f"{chapter} unexpectedly reports insufficient data"
        if chapter == "general":
            # general.py has exactly one check (closed_status); a CURRENT
            # company legitimately produces zero observations -- that's
            # this chapter's whole scope, not data loss.
            continue
        assert result.observations or result.factors, (
            f"{chapter} produced nothing for a card built to trigger it"
        )


async def test_financial_and_legal_facts_do_not_cross_chapters() -> None:
    """Concrete instance of the isolation guarantee: the specific loss
    figure only shows up under finance, the specific arbitration amount
    only shows up under legal -- not swapped or duplicated across both."""
    card = _rich_card()
    results = await _run_all(card)

    finance_values = _all_evidence_values(results["finance"])
    legal_values = _all_evidence_values(results["legal"])

    assert -333_333.0 in finance_values  # raw profit value, not abs()
    assert -333_333.0 not in legal_values
    assert 777_777.0 in legal_values
    assert 777_777.0 not in finance_values


async def test_awaitable_analyzer_results_are_supported() -> None:
    """analyzers.ANALYZERS may map to sync or async callables (analyzers.py
    checks `inspect.isawaitable`) -- confirm every registered tool is
    actually callable through that same contract the MCP server/client use."""
    card = _rich_card()
    for tool_name in TOOL_NAMES:
        outcome = ANALYZERS[tool_name](card)
        if inspect.isawaitable(outcome):
            outcome = await outcome
        assert outcome.chapter == tool_name.removeprefix("analyze_")
