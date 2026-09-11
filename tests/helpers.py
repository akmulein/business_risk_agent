from counterparty_verification.domain import CounterpartyCard


class InMemoryRepository:
    """Test adapter: no filesystem, database or network access."""

    def __init__(self, cards: list[CounterpartyCard]):
        self.cards = {card.company_reports.inn: card for card in cards}

    async def get_by_inn(self, inn):
        return self.cards.get(inn)

    async def get_many_by_inns(self, inns):
        return [self.cards[inn] for inn in inns if inn in self.cards]

    async def get_source_report_by_inn(self, inn):
        card = self.cards.get(inn)
        return card.company_reports.raw_report_json if card else None
