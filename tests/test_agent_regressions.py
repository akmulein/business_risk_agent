from types import SimpleNamespace

import pytest

from counterparty_verification.agents import (
    ReputationAggregateOutput,
    ReputationAgent,
    ReputationHighlight,
)
from counterparty_verification.reputation_rules import build_view
from counterparty_verification.settings import Settings


class FakeAgent:
    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.calls = 0

    async def run(self, _prompt):
        self.calls += 1
        output = next(self.outputs)
        if isinstance(output, Exception):
            raise output
        return SimpleNamespace(output=output)


@pytest.mark.asyncio
async def test_reputation_agent_retries_invalid_evidence(card) -> None:
    view = build_view(card)
    field = view.indexed[0].field("name")
    chapter = view.indexed[0].chapter
    invalid = ReputationAggregateOutput(
        highlights=[
            ReputationHighlight(
                chapter=chapter,
                title="Фактор",
                text="Описание",
                evidence_fields=["risk_factors[999].name"],
            )
        ]
    )
    valid = ReputationAggregateOutput(
        highlights=[
            ReputationHighlight(
                chapter=chapter,
                title="Фактор",
                text="Описание",
                evidence_fields=[field],
            )
        ]
    )
    model = FakeAgent([invalid, valid])
    agent = ReputationAgent(Settings(openrouter_api_key=None))
    agent.agent = model

    observations = await agent.aggregate(view)

    assert model.calls == 2
    assert observations[0].evidence[0].field == field


def assert_source_fallback(observations, view):
    assert [item.code for item in observations] == [
        f"chapter_{chapter}" for chapter in view.chapters
    ]
    for item, entries in zip(observations, view.by_chapter.values(), strict=True):
        assert item.detail == "; ".join(dict.fromkeys(entry.item.name for entry in entries))
        assert item.evidence == [entry.evidence("name") for entry in entries]


@pytest.mark.asyncio
async def test_reputation_disabled_keeps_source_facts(card):
    view = build_view(card)
    agent = ReputationAgent(Settings(openrouter_api_key=None))
    assert_source_fallback(await agent.aggregate(view), view)


@pytest.mark.asyncio
async def test_reputation_model_error_falls_back_without_retry(card):
    view = build_view(card)
    agent = ReputationAgent(Settings(openrouter_api_key=None))
    agent.agent = FakeAgent([ConnectionError("model unavailable")])
    assert_source_fallback(await agent.aggregate(view), view)
    assert agent.agent.calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_kind", ["empty", "unknown_chapter", "missing_evidence", "cross_chapter"])
async def test_reputation_invalid_output_has_bounded_retries(card, invalid_kind):
    if invalid_kind == "cross_chapter":
        other = card.risk_factors[0].model_copy(update={"chapter": "another_chapter"})
        card = card.model_copy(update={"risk_factors": [*card.risk_factors, other]})
    view = build_view(card)
    first = view.indexed[0]
    chapter = first.chapter
    fields = [first.field("name")]
    if invalid_kind == "unknown_chapter":
        chapter = "not_a_source_chapter"
    elif invalid_kind == "missing_evidence":
        fields = []
    elif invalid_kind == "cross_chapter":
        other = next(entry for entry in view.indexed if entry.chapter != chapter)
        fields = [other.field("name")]
    output = ReputationAggregateOutput(highlights=[] if invalid_kind == "empty" else [
        ReputationHighlight(chapter=chapter, title="Недостоверно", text="Не принимать", evidence_fields=fields)
    ])
    agent = ReputationAgent(Settings(openrouter_api_key=None))
    agent.agent = FakeAgent([output, output, output])
    assert_source_fallback(await agent.aggregate(view), view)
    assert agent.agent.calls == 3


@pytest.mark.asyncio
async def test_reputation_empty_input_does_not_call_model(card):
    card = card.model_copy(update={"risk_factors": []})
    agent = ReputationAgent(Settings(openrouter_api_key=None))
    agent.agent = FakeAgent([])
    assert await agent.aggregate(build_view(card)) == []
    assert agent.agent.calls == 0


@pytest.mark.asyncio
async def test_reputation_cancellation_is_not_swallowed(card):
    import asyncio

    class CancelledModel:
        async def run(self, prompt):
            raise asyncio.CancelledError()

    agent = ReputationAgent(Settings(openrouter_api_key=None))
    agent.agent = CancelledModel()
    with pytest.raises(asyncio.CancelledError):
        await agent.aggregate(build_view(card))
