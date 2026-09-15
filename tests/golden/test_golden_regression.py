"""Level 3 (deterministic half): run every golden case through the real 6
tools and check the ground truth recorded in `tests/golden/cases.py` --
no LLM involved. This is the fast, free, always-on regression gate; the
small live agent evaluation lives in `eval/`.
"""

from __future__ import annotations

import pytest

from app.analysis.service import TOOL_NAMES
from app.domain import CounterpartyCard
from app.mcp.client import LocalAnalysisToolClient
from tests.golden.cases import ALL_CASES, GoldenCase


async def _run_all(card: CounterpartyCard) -> dict[str, object]:
    client = LocalAnalysisToolClient()
    results = {}
    for tool_name in TOOL_NAMES:
        result = await client.call(tool_name, card)
        results[result.chapter] = result
    return results


def _all_evidence_values(results: dict[str, object]) -> set:
    values: set = set()
    for result in results.values():
        values.update(item.value for item in result.evidence)
        for observation in result.observations:
            values.update(item.value for item in observation.evidence)
        for factor in result.factors:
            values.update(item.value for item in factor.evidence)
    return values


def _observation_codes(result) -> set[str]:
    return {item.code for item in result.observations}


@pytest.mark.parametrize("case", ALL_CASES, ids=lambda case: case.id)
async def test_required_signals_fire(case: GoldenCase) -> None:
    results = await _run_all(case.card)
    for chapter, code in case.required_signals:
        assert chapter in results, f"{case.id}: chapter {chapter!r} did not run"
        assert code in _observation_codes(results[chapter]), (
            f"{case.id}: expected observation {code!r} in chapter {chapter!r}, "
            f"got {sorted(_observation_codes(results[chapter]))}"
        )


@pytest.mark.parametrize("case", ALL_CASES, ids=lambda case: case.id)
async def test_forbidden_signals_do_not_fire(case: GoldenCase) -> None:
    results = await _run_all(case.card)
    for chapter, code in case.forbidden_signals:
        if chapter not in results:
            continue
        assert code not in _observation_codes(results[chapter]), (
            f"{case.id}: observation {code!r} must not fire in chapter {chapter!r}"
        )


@pytest.mark.parametrize("case", ALL_CASES, ids=lambda case: case.id)
async def test_expected_insufficient_chapters_are_reported_as_such(case: GoldenCase) -> None:
    results = await _run_all(case.card)
    for chapter in case.expected_insufficient_chapters:
        assert chapter in results, f"{case.id}: chapter {chapter!r} did not run"
        assert not results[chapter].data_sufficient, (
            f"{case.id}: chapter {chapter!r} was expected to report insufficient data"
        )


@pytest.mark.parametrize("case", ALL_CASES, ids=lambda case: case.id)
async def test_exact_numeric_values_are_traceable_in_evidence(case: GoldenCase) -> None:
    if not case.exact_numeric_values:
        pytest.skip("case has no numeric fingerprints to trace")
    results = await _run_all(case.card)
    all_values = _all_evidence_values(results)
    for label, expected in case.exact_numeric_values.items():
        assert any(
            isinstance(value, (int, float)) and not isinstance(value, bool)
            and abs(float(value) - expected) < 0.5
            for value in all_values
        ), f"{case.id}: {label} ({expected}) not found in any chapter's evidence"


def test_case_ids_are_unique() -> None:
    ids = [case.id for case in ALL_CASES]
    assert len(ids) == len(set(ids))


def test_maksmarket_case_is_present_with_the_mandated_facts() -> None:
    """Directly pins the numbers from the task spec, independent of the
    generic exact_numeric_values loop above -- if this fixture ever drifts
    from the real seed record, this is the one test that should fail
    loudly and specifically."""
    from tests.golden.cases import CASE_MAKSMARKET

    card = CASE_MAKSMARKET.card
    assert card.company_reports.inn == "5032257375"
    assert card.company_reports.short_name == 'ООО "МАКСМАРКЕТ"'
    assert "банкрот" in (card.company_reports.status_reason or "").lower()
    assert card.company_reports.risk_level == "LOW"

    arb = card.arbitration[0]
    assert arb.role == "defendant"
    assert arb.source == "yearly"
    assert arb.case_status == "all"
    assert arb.year == 2024
    assert arb.case_count == 258
    assert arb.amount == 2_589_790_444

    codes_by_sign = {(f.sign, f.code) for f in card.risk_factors}
    assert ("negative", "executionProceedings") in codes_by_sign
    assert ("negative", "fnsBlocking") in codes_by_sign
    assert ("negative", "invalidAddress") in codes_by_sign
    assert ("negative", "invalidRegistrationData") in codes_by_sign
    assert ("positive", "massAddress") in codes_by_sign  # massAddress=false, NOT negative
