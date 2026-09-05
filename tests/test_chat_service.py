import pytest

from counterparty_verification.chat_models import (
    ChatAgentResult,
    ChatRole,
    ChatSource,
)
from counterparty_verification.chat_service import (
    ChatService,
    InMemoryChatSessionStore,
)
from counterparty_verification.domain import (
    AnalysisResponse,
    BatchAnalysisItem,
    BatchAnalysisResponse,
    BatchAnalysisStatus,
    CounterpartyCard,
    RiskLevel,
)


class StubRepository:
    def __init__(self, cards: list[CounterpartyCard]) -> None:
        self.cards = {card.company_reports.inn: card for card in cards}
        self.requested: list[list[str]] = []

    async def get_by_inn(self, inn: str) -> CounterpartyCard | None:
        return self.cards.get(inn)

    async def get_many_by_inns(self, inns: list[str]) -> list[CounterpartyCard]:
        self.requested.append(inns)
        return [self.cards[inn] for inn in inns if inn in self.cards]


class StubChatAgent:
    def __init__(self) -> None:
        self.calls = []

    async def answer(self, question, cards, analyses, history):
        self.calls.append(
            {
                "question": question,
                "inns": [card.company_reports.inn for card in cards],
                "analysis_inns": list(analyses),
                "history": history,
            }
        )
        inn = cards[0].company_reports.inn
        return ChatAgentResult(
            answer=f"Ответ по {len(cards)} контрагентам",
            sources=[
                ChatSource(
                    inn=inn,
                    field="company_reports.inn",
                    value=inn,
                )
            ],
        )


def make_analysis(card: CounterpartyCard) -> AnalysisResponse:
    return AnalysisResponse(
        analysis_id=f"analysis-{card.company_reports.inn}",
        inn=card.company_reports.inn,
        summary="Саммари",
        risk_level=RiskLevel.LOW,
        chapters=[],
    )


@pytest.mark.asyncio
async def test_chat_supports_multiple_companies_and_history(
    card: CounterpartyCard,
) -> None:
    second = card.model_copy(deep=True)
    second.company_reports.inn = "772377037026"
    second.company_reports.full_name = "ИП КАСАТКИН"
    cards = [card, second]
    response = BatchAnalysisResponse(
        results=[
            BatchAnalysisItem(
                inn=item.company_reports.inn,
                status=BatchAnalysisStatus.SUCCESS,
                analysis=make_analysis(item),
            )
            for item in cards
        ]
    )
    repository = StubRepository(cards)
    store = InMemoryChatSessionStore(ttl_seconds=60)
    agent = StubChatAgent()
    service = ChatService(
        repository=repository,
        store=store,
        agent=agent,
        timeout_seconds=5,
        history_limit=12,
    )

    chat_id = await service.create_for_analysis(response)
    assert chat_id is not None

    first = await service.answer(chat_id, "Сравни компании")
    second_answer = await service.answer(chat_id, "А какая безопаснее?")
    history = await service.history(chat_id)

    assert first.answer == "Ответ по 2 контрагентам"
    assert second_answer.answer == "Ответ по 2 контрагентам"
    assert repository.requested == [
        [card.company_reports.inn, second.company_reports.inn],
        [card.company_reports.inn, second.company_reports.inn],
    ]
    assert agent.calls[0]["inns"] == [
        card.company_reports.inn,
        second.company_reports.inn,
    ]
    assert agent.calls[0]["history"] == []
    assert [message.role for message in agent.calls[1]["history"]] == [
        ChatRole.USER,
        ChatRole.ASSISTANT,
    ]
    assert [message.role for message in history.messages] == [
        ChatRole.USER,
        ChatRole.ASSISTANT,
        ChatRole.USER,
        ChatRole.ASSISTANT,
    ]
    assert history.inns == [
        card.company_reports.inn,
        second.company_reports.inn,
    ]


@pytest.mark.asyncio
async def test_chat_is_not_created_when_no_reports_are_found(
    card: CounterpartyCard,
) -> None:
    service = ChatService(
        repository=StubRepository([card]),
        store=InMemoryChatSessionStore(ttl_seconds=60),
        agent=StubChatAgent(),
        timeout_seconds=5,
        history_limit=12,
    )
    response = BatchAnalysisResponse(
        results=[
            BatchAnalysisItem(
                inn="772377037026",
                status=BatchAnalysisStatus.NOT_FOUND,
                error="Не найден",
            )
        ]
    )

    assert await service.create_for_analysis(response) is None
