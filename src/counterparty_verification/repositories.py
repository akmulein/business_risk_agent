import json
from pathlib import Path
from typing import Protocol

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    Float,
    ForeignKeyConstraint,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from .domain import CounterpartyCard


class CounterpartyRepository(Protocol):
    async def get_by_inn(self, inn: str) -> CounterpartyCard | None: ...


class JsonCounterpartyRepository:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    async def get_by_inn(self, inn: str) -> CounterpartyCard | None:
        with self.path.open(encoding="utf-8") as source:
            records = json.load(source)
        for record in records:
            card = CounterpartyCard.model_validate(record)
            if card.company_reports.inn == inn:
                return card
        return None


metadata = MetaData()
company_reports = Table(
    "company_reports",
    metadata,
    Column("report_id", String, primary_key=True),
    Column("report_date", Date),
    Column("inn", String(10), nullable=False, index=True),
    Column("ogrn", String),
    Column("short_name", String),
    Column("full_name", String),
    Column("risk_level", String),
    Column("zsk_risk_level", String),
    Column("kpp", String),
    Column("okpo", String),
    Column("address", String),
    Column("email", String),
    Column("website", String),
    Column("company_size", String),
    Column("staff", String),
    Column("registration_date", Date),
    Column("years_from_registration", Integer),
    Column("status", String),
    Column("status_reason", String),
    Column("status_date", Date),
    Column("share_capital", Float),
    Column("branches_count", Integer),
    Column("raw_report_json", JSONB, nullable=False, default=dict),
    UniqueConstraint("report_id", "inn"),
)


def _child_columns(
    *columns: Column, report_id_primary_key: bool = False
) -> tuple[Column | ForeignKeyConstraint, ...]:
    return (
        Column(
            "report_id",
            String,
            primary_key=report_id_primary_key,
            nullable=False,
        ),
        Column("company_inn", String(10), nullable=False),
        *columns,
        ForeignKeyConstraint(
            ["report_id", "company_inn"],
            ["company_reports.report_id", "company_reports.inn"],
        ),
    )


structure_items = Table(
    "structure_items",
    metadata,
    Column("id", String, primary_key=True),
    *_child_columns(
        Column("subject_inn", String(10)),
        Column("item_type", String, nullable=False),
        Column("item_index", Integer, nullable=False),
        Column("name", String),
        Column("related_inn", String(10)),
        Column("related_ogrn", String),
        Column("role", String),
        Column("position", String),
        Column("code", String),
        Column("description", String),
        Column("share", Float),
        Column("amount", Float),
        Column("date_from", Date),
        Column("active", Boolean),
        Column("registration_date", Date),
        Column("address", String),
        Column("phone_type", String),
        Column("phone_code", String),
        Column("phone_number", String),
        Column("auth_person_name", String),
        Column("auth_person_position", String),
        Column("details_json", JSON, nullable=False, default=dict),
    ),
)

financial_reports = Table(
    "financial_reports",
    metadata,
    *_child_columns(
        Column("year", Integer, primary_key=True),
        Column("proceeds", Float),
        Column("profit", Float),
        Column("total_assets", Float),
        Column("current_assets_total", Float),
        Column("stocks", Float),
        Column("receivables", Float),
        Column("bankroll", Float),
        Column("uncurrent_assets_total", Float),
        Column("fixed_assets", Float),
        Column("total_liabilities", Float),
        Column("capitals", Float),
        Column("long_term_duties_total", Float),
        Column("long_term_duties_others", Float),
        Column("short_term_liabilities_total", Float),
        Column("borrowed_funds", Float),
        Column("accounts_payable", Float),
        Column("sustainability", Float),
        Column("solvency", Float),
        Column("profitability", Float),
        report_id_primary_key=True,
    ),
)

risk_factors = Table(
    "risk_factors",
    metadata,
    *_child_columns(
        Column("sign", String, primary_key=True),
        Column("item_index", Integer, primary_key=True),
        Column("code", String),
        Column("name", String, nullable=False),
        Column("chapter", String),
        report_id_primary_key=True,
    ),
)

arbitration = Table(
    "arbitration",
    metadata,
    Column("id", String, primary_key=True),
    *_child_columns(
        Column("source", String, nullable=False),
        Column("year", Integer),
        Column("role", String, nullable=False),
        Column("case_status", String, nullable=False),
        Column("case_count", Integer, nullable=False),
        Column("amount", Float),
    ),
)

legal_events = Table(
    "legal_events",
    metadata,
    *_child_columns(
        Column("event_type", String, primary_key=True),
        Column("item_index", Integer, primary_key=True),
        Column("external_id", String),
        Column("event_date", Date),
        Column("end_date", Date),
        Column("active", Boolean),
        Column("status", String),
        Column("amount", Float),
        Column("title", String),
        Column("authority", String),
        Column("form", String),
        Column("details_json", JSON, nullable=False, default=dict),
        report_id_primary_key=True,
    ),
)

procurements = Table(
    "procurements",
    metadata,
    *_child_columns(
        Column("item_index", Integer, primary_key=True),
        Column("year", Integer, nullable=False),
        Column("federal_law_code", String),
        Column("tender_admitted_count", Integer),
        Column("tender_winner_count", Integer),
        Column("contract_signed_count", Integer),
        Column("contract_signed_amount", Float),
        report_id_primary_key=True,
    ),
)

CHILD_TABLES = (
    structure_items,
    financial_reports,
    risk_factors,
    arbitration,
    legal_events,
    procurements,
)


class PostgresCounterpartyRepository:
    """Loads the latest normalized report and assembles a domain aggregate."""

    def __init__(self, database_url: str, engine: AsyncEngine | None = None) -> None:
        self.engine = engine or create_async_engine(database_url, pool_pre_ping=True)

    async def get_by_inn(self, inn: str) -> CounterpartyCard | None:
        async with self.engine.connect() as connection:
            report_row = (
                await connection.execute(
                    select(company_reports)
                    .where(company_reports.c.inn == inn)
                    .order_by(
                        company_reports.c.report_date.desc().nullslast(),
                        company_reports.c.report_id.desc(),
                    )
                    .limit(1)
                )
            ).mappings().first()
            if report_row is None:
                return None
            report_id = report_row["report_id"]
            children: dict[str, list[dict]] = {}
            for table in CHILD_TABLES:
                rows = (
                    await connection.execute(
                        select(table).where(
                            table.c.report_id == report_id,
                            table.c.company_inn == inn,
                        )
                    )
                ).mappings().all()
                children[table.name] = [dict(row) for row in rows]
        return CounterpartyCard.model_validate(
            {
                "company_reports": dict(report_row),
                **children,
            }
        )
