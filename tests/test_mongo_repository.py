from counterparty_verification.repositories import MongoCounterpartyRepository


class FakeCollection:
    def __init__(self, document):
        self.document = document
        self.calls = []

    async def find_one(self, query, projection, sort):
        self.calls.append((query, projection, sort))
        return self.document


class FakeDatabase:
    def __init__(self, collection):
        self.collection = collection

    def __getitem__(self, name):
        assert name == "counterparty_cards"
        return self.collection


class FakeClient:
    def __init__(self, collection):
        self.database = FakeDatabase(collection)
        self.closed = False

    def __getitem__(self, name):
        assert name == "counterparties"
        return self.database

    async def close(self):
        self.closed = True


async def test_mongo_repository_loads_prebuilt_card(card):
    document = card.model_dump(mode="python")
    collection = FakeCollection(document)
    client = FakeClient(collection)
    repository = MongoCounterpartyRepository(
        "mongodb://unused",
        "counterparties",
        "counterparty_cards",
        client=client,
    )

    loaded = await repository.get_by_inn(card.company_reports.inn)

    assert loaded == card
    assert collection.calls == [
        (
            {"company_reports.inn": card.company_reports.inn},
            {"_id": False},
            [("company_reports.report_date", -1)],
        )
    ]

    await repository.close()
    assert client.closed is True


async def test_mongo_repository_returns_none():
    repository = MongoCounterpartyRepository(
        "mongodb://unused",
        "counterparties",
        "counterparty_cards",
        client=FakeClient(FakeCollection(None)),
    )

    assert await repository.get_by_inn("7707083893") is None
