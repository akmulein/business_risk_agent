from types import SimpleNamespace

import pytest

from counterparty_verification.agents import (
    GroundedText,
    ReputationAggregateOutput,
    ReputationAgent,
    ReputationHighlight,
    SpecialistAgent,
)
from counterparty_verification.domain import ChapterResult, Evidence
from counterparty_verification.reputation_rules import build_view
from counterparty_verification.settings import Settings


class FakeAgent:
    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.calls = 0

    async def run(self, _prompt):
        self.calls += 1
        output = next(self.outputs)
        return SimpleNamespace(output=output)


@pytest.mark.asyncio
async def test_specialist_uses_real_chapter_field_name() -> None:
    specialist = SpecialistAgent(Settings(openrouter_api_key=None))
    specialist.agent = FakeAgent(
        [
            GroundedText(
                text="Проверка выполнена.",
                evidence_fields=["company_reports.inn"],
            )
        ]
    )
    chapter = ChapterResult(
        chapter="general",
        conclusion="Исходное заключение.",
        evidence=[Evidence(field="company_reports.inn", value="7700000000")],
    )

    result = await specialist.enrich(chapter)

    assert result.chapter == "general"
    assert result.conclusion == "Проверка выполнена."


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
