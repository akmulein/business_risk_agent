import json

import pytest

from counterparty_verification.chat_agent import (
    ChatModelCitation,
    ChatModelNotConfiguredError,
    ChatModelOutput,
    ReportChatAgent,
    flatten_evidence,
)
from counterparty_verification.domain import CounterpartyCard
from counterparty_verification.settings import Settings


class FakeRunResult:
    def __init__(self, output: ChatModelOutput) -> None:
        self.output = output


class FakeModelAgent:
    def __init__(self, output: ChatModelOutput) -> None:
        self.output = output
        self.payload = None

    async def run(self, payload: str) -> FakeRunResult:
        self.payload = json.loads(payload)
        return FakeRunResult(self.output)


@pytest.mark.asyncio
async def test_chat_agent_returns_only_verified_sources(
    card: CounterpartyCard,
) -> None:
    model = FakeModelAgent(
        ChatModelOutput(
            answer="ИНН компании указан в отчёте.",
            citations=[
                ChatModelCitation(
                    inn=card.company_reports.inn,
                    field="company_reports.inn",
                )
            ],
        )
    )
    agent = ReportChatAgent(
        Settings(openrouter_api_key=None),
        model_agent=model,
    )

    result = await agent.answer("Какой ИНН?", [card], {}, [])

    assert result.answer == "ИНН компании указан в отчёте."
    assert result.sources[0].inn == card.company_reports.inn
    assert result.sources[0].field == "company_reports.inn"
    assert result.sources[0].value == card.company_reports.inn
    assert model.payload["reports"][0]["inn"] == card.company_reports.inn


@pytest.mark.asyncio
async def test_chat_agent_rejects_unknown_source(
    card: CounterpartyCard,
) -> None:
    model = FakeModelAgent(
        ChatModelOutput(
            answer="Неподтверждённый ответ",
            citations=[
                ChatModelCitation(
                    inn=card.company_reports.inn,
                    field="company_reports.nonexistent",
                )
            ],
        )
    )
    agent = ReportChatAgent(
        Settings(openrouter_api_key=None),
        model_agent=model,
    )

    result = await agent.answer("Вопрос", [card], {}, [])

    assert "нет подтверждения" in result.answer
    assert result.sources == []


@pytest.mark.asyncio
async def test_chat_agent_requires_openrouter_key(
    card: CounterpartyCard,
) -> None:
    agent = ReportChatAgent(Settings(openrouter_api_key=None))

    with pytest.raises(ChatModelNotConfiguredError):
        await agent.answer("Вопрос", [card], {}, [])


def test_flatten_evidence_preserves_empty_collections() -> None:
    fields = flatten_evidence({"arbitration": [], "details": {}})

    assert fields == {"arbitration": [], "details": {}}
