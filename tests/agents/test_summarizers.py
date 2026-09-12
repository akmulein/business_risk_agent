import asyncio
import json

import pytest
from pydantic_ai.messages import ModelResponse, TextPart, UserPromptPart
from pydantic_ai.models.function import FunctionModel

from counterparty_verification.agents import comparison, evaluator
from counterparty_verification.analysis.comparison import build_comparison
from counterparty_verification.analysis.service import TOOL_NAMES
from counterparty_verification.domain import (
    ChapterResult,
    Evidence,
    Observation,
    RiskLevel,
)
from counterparty_verification.mcp.client import LocalAnalysisToolClient
from counterparty_verification.settings import Settings


@pytest.fixture
async def chapters(card):
    client = LocalAnalysisToolClient()
    return await asyncio.gather(*(client.call(name, card) for name in TOOL_NAMES))


def make_agent(monkeypatch, kind, callback):
    module = evaluator if kind == "individual" else comparison
    monkeypatch.setattr(module, "_model", lambda settings: FunctionModel(callback))
    cls = (
        evaluator.EvaluatorAgent if kind == "individual" else comparison.ComparisonAgent
    )
    return cls(Settings(openrouter_api_key="test-only"))


async def summarize(agent, kind, card, chapters):
    if kind == "individual":
        return (await agent.summarize("Компания", RiskLevel.MEDIUM, chapters)).summary
    companies = build_comparison([card]).companies
    return await agent.summarize(companies, {card.company_reports.inn: chapters})


@pytest.mark.parametrize("kind", ["individual", "comparison"])
async def test_summaries_accept_plain_text_without_citation_or_sentence_limits(
    monkeypatch, kind, card, chapters
):
    text = "Произвольный текст модели с числом 987654321. " * 40
    calls = []
    payloads = []

    def model(messages, info):
        calls.append(info)
        payloads.append(
            json.loads(
                next(
                    part.content
                    for message in reversed(messages)
                    for part in message.parts
                    if isinstance(part, UserPromptPart)
                )
            )
        )
        return ModelResponse(parts=[TextPart(text)])

    agent = make_agent(monkeypatch, kind, model)
    result = await summarize(agent, kind, card, chapters)

    assert result == text.strip()
    assert len(calls) == 1
    assert not calls[0].output_tools
    payload = payloads[0]
    report = payload if kind == "individual" else payload["companies"][0]
    assert [item["chapter"] for item in report["chapters"]] == [
        name.removeprefix("analyze_") for name in TOOL_NAMES
    ]
    assert "fact_refs" not in json.dumps(payload)
    assert "fact_ids" not in json.dumps(payload)


@pytest.mark.parametrize("kind", ["individual", "comparison"])
async def test_payload_carries_no_raw_enum_values(monkeypatch, kind, card, chapters):
    """A model can only repeat what it was given, so statuses reach it already
    spelled out in Russian -- never as LOW, HIGH or ISSUE."""
    prompts = []

    def model(messages, info):
        prompts.append(
            next(
                part.content
                for message in reversed(messages)
                for part in message.parts
                if isinstance(part, UserPromptPart)
            )
        )
        return ModelResponse(parts=[TextPart("Сводка")])

    agent = make_agent(monkeypatch, kind, model)
    await summarize(agent, kind, card, chapters)

    for value in ("LOW", "MEDIUM", "HIGH", "UNKNOWN", "ISSUE", "NO_DATA"):
        assert value not in prompts[0]


@pytest.mark.parametrize("kind", ["individual", "comparison"])
async def test_summary_model_error_is_not_retried(monkeypatch, kind, card, chapters):
    calls = []

    def model(messages, info):
        calls.append(True)
        raise ConnectionError("unavailable")

    agent = make_agent(monkeypatch, kind, model)
    with pytest.raises(ConnectionError):
        await summarize(agent, kind, card, chapters)
    assert len(calls) == 1


@pytest.mark.parametrize("kind", ["individual", "comparison"])
async def test_empty_summary_is_an_error(monkeypatch, kind, card, chapters):
    def model(messages, info):
        return ModelResponse(parts=[TextPart("   ")])

    agent = make_agent(monkeypatch, kind, model)
    with pytest.raises(RuntimeError, match="empty summary"):
        await summarize(agent, kind, card, chapters)


@pytest.mark.parametrize("kind", ["individual", "comparison"])
async def test_summary_without_key_fails_for_service_fallback(kind, card, chapters):
    cls = (
        evaluator.EvaluatorAgent if kind == "individual" else comparison.ComparisonAgent
    )
    agent = cls(Settings(openrouter_api_key=""))
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        await summarize(agent, kind, card, chapters)


@pytest.mark.parametrize("count", [2, 5, 10])
async def test_comparison_passes_every_company_and_its_tool_results(
    monkeypatch, card, count
):
    cards = [
        card.model_copy(
            update={
                "company_reports": card.company_reports.model_copy(
                    update={
                        "inn": str(7700000000 + index),
                        "short_name": f"Компания {index}",
                    }
                )
            }
        )
        for index in range(count)
    ]
    chapters_by_inn = {
        item.company_reports.inn: [
            ChapterResult(
                chapter="legal",
                conclusion=f"Результат {item.company_reports.inn}",
                data_sufficient=False,
                error="ConnectionError",
                observations=[
                    Observation(
                        code="source",
                        title="Наблюдение",
                        detail="Исходное наблюдение тула",
                        evidence=[Evidence(field="field", value="DO_NOT_DUPLICATE")],
                    )
                ],
            )
        ]
        for item in cards
    }
    payloads = []

    def model(messages, info):
        payloads.append(json.loads(messages[-1].parts[0].content))
        return ModelResponse(parts=[TextPart("Сравнение")])

    agent = make_agent(monkeypatch, "comparison", model)
    companies = build_comparison(cards).companies
    assert await agent.summarize(companies, chapters_by_inn) == "Сравнение"
    reports = payloads[0]["companies"]
    assert len(reports) == count
    assert "DO_NOT_DUPLICATE" not in json.dumps(payloads[0])
    for report in reports:
        inn = report["report"]["inn"]
        chapter = report["chapters"][0]
        assert chapter["conclusion"] == f"Результат {inn}"
        assert chapter["observations"][0]["detail"] == "Исходное наблюдение тула"
        assert chapter["data_sufficient"] is False
        assert chapter["error"] == "ConnectionError"
