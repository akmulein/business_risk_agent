from counterparty_verification.repositories import MongoCounterpartyRepository


class FakeCursor:
    def __init__(self, documents):
        self.documents = documents
        self.sort_spec = None

    def sort(self, sort_spec):
        self.sort_spec = sort_spec
        return self

    async def to_list(self, length):
        assert length is None
        return self.documents


class FakeCollection:
    def __init__(self, document):
        self.document = document
        self.calls = []
        self.find_calls = []
        self.last_cursor = None

    async def find_one(self, query, projection, sort):
        self.calls.append((query, projection, sort))
        return self.document

    def find(self, query, projection):
        self.find_calls.append((query, projection))
        documents = [] if self.document is None else [self.document]
        self.last_cursor = FakeCursor(documents)
        return self.last_cursor


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


async def test_mongo_repository_loads_many_cards_in_request_order(card):
    document = card.model_dump(mode="python")
    collection = FakeCollection(document)
    repository = MongoCounterpartyRepository(
        "mongodb://unused",
        "counterparties",
        "counterparty_cards",
        client=FakeClient(collection),
    )
    inns = ["772377037026", card.company_reports.inn]

    loaded = await repository.get_many_by_inns(inns)

    assert loaded == [card]
    assert collection.find_calls == [
        (
            {"company_reports.inn": {"$in": inns}},
            {"_id": False},
        )
    ]
    assert collection.last_cursor.sort_spec == [
        ("company_reports.inn", 1),
        ("company_reports.report_date", -1),
    ]
