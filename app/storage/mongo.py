from inspect import isawaitable
from typing import Any

from app.domain import CounterpartyCard


class MongoCounterpartyRepository:
    """Loads an application-ready card; raw source reports stay untouched."""

    def __init__(
        self,
        mongodb_url: str,
        database: str,
        collection: str,
        source_collection: str = "reports",
        client: Any | None = None,
    ) -> None:
        if client is None:
            from pymongo import AsyncMongoClient

            client = AsyncMongoClient(mongodb_url)
        self.client = client
        self.database = client[database]
        self.collection = self.database[collection]
        self.source_collection_name = source_collection

    async def get_by_inn(self, inn: str) -> CounterpartyCard | None:
        document = await self.collection.find_one(
            {"company_reports.inn": inn},
            projection={"_id": False},
            sort=[("company_reports.report_date", -1)],
        )
        if document is None:
            return None
        return CounterpartyCard.model_validate(document)

    async def get_many_by_inns(self, inns: list[str]) -> list[CounterpartyCard]:
        cursor = self.collection.find(
            {"company_reports.inn": {"$in": inns}},
            projection={"_id": False},
        ).sort(
            [
                ("company_reports.inn", 1),
                ("company_reports.report_date", -1),
            ]
        )
        documents = await cursor.to_list(length=None)
        latest: dict[str, dict[str, Any]] = {}
        for document in documents:
            inn = document["company_reports"]["inn"]
            latest.setdefault(inn, document)
        return [
            CounterpartyCard.model_validate(latest[inn])
            for inn in inns
            if inn in latest
        ]

    async def get_source_report_by_inn(self, inn: str) -> dict[str, Any] | None:
        document = await self.database[self.source_collection_name].find_one(
            {"report.baseInfo.inn": inn},
            projection={"_id": False, "report": True},
            sort=[("report.reportDate", -1)],
        )
        if document is None:
            return None
        report = document.get("report")
        return report if isinstance(report, dict) else None

    async def close(self) -> None:
        result = self.client.close()
        if isawaitable(result):
            await result
