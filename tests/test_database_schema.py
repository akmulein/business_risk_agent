from counterparty_verification.repositories import (
    arbitration,
    company_reports,
    financial_reports,
    legal_events,
    procurements,
    risk_factors,
    structure_items,
)


EXPECTED_COLUMNS = {
    "company_reports": {
        "report_id",
        "report_date",
        "inn",
        "ogrn",
        "short_name",
        "full_name",
        "risk_level",
        "zsk_risk_level",
        "kpp",
        "okpo",
        "address",
        "email",
        "website",
        "company_size",
        "staff",
        "registration_date",
        "years_from_registration",
        "status",
        "status_reason",
        "status_date",
        "share_capital",
        "branches_count",
        "raw_report_json",
    },
    "structure_items": {
        "id",
        "report_id",
        "company_inn",
        "subject_inn",
        "item_type",
        "item_index",
        "name",
        "related_inn",
        "related_ogrn",
        "role",
        "position",
        "code",
        "description",
        "share",
        "amount",
        "date_from",
        "active",
        "registration_date",
        "address",
        "phone_type",
        "phone_code",
        "phone_number",
        "auth_person_name",
        "auth_person_position",
        "details_json",
    },
    "financial_reports": {
        "report_id",
        "company_inn",
        "year",
        "proceeds",
        "profit",
        "total_assets",
        "current_assets_total",
        "stocks",
        "receivables",
        "bankroll",
        "uncurrent_assets_total",
        "fixed_assets",
        "total_liabilities",
        "capitals",
        "long_term_duties_total",
        "long_term_duties_others",
        "short_term_liabilities_total",
        "borrowed_funds",
        "accounts_payable",
        "sustainability",
        "solvency",
        "profitability",
    },
    "risk_factors": {
        "report_id",
        "company_inn",
        "sign",
        "item_index",
        "code",
        "name",
        "chapter",
    },
    "arbitration": {
        "id",
        "report_id",
        "company_inn",
        "source",
        "year",
        "role",
        "case_status",
        "case_count",
        "amount",
    },
    "legal_events": {
        "report_id",
        "company_inn",
        "event_type",
        "item_index",
        "external_id",
        "event_date",
        "end_date",
        "active",
        "status",
        "amount",
        "title",
        "authority",
        "form",
        "details_json",
    },
    "procurements": {
        "report_id",
        "company_inn",
        "item_index",
        "year",
        "federal_law_code",
        "tender_admitted_count",
        "tender_winner_count",
        "contract_signed_count",
        "contract_signed_amount",
    },
}

EXPECTED_PRIMARY_KEYS = {
    "company_reports": {"report_id"},
    "structure_items": {"id"},
    "financial_reports": {"report_id", "year"},
    "risk_factors": {"report_id", "sign", "item_index"},
    "arbitration": {"id"},
    "legal_events": {"report_id", "event_type", "item_index"},
    "procurements": {"report_id", "item_index"},
}


def test_database_tables_match_data_dictionary() -> None:
    tables = (
        company_reports,
        structure_items,
        financial_reports,
        risk_factors,
        arbitration,
        legal_events,
        procurements,
    )

    for table in tables:
        assert set(table.c.keys()) == EXPECTED_COLUMNS[table.name]
        assert {column.name for column in table.primary_key} == (
            EXPECTED_PRIMARY_KEYS[table.name]
        )


def test_child_tables_use_composite_report_foreign_key() -> None:
    for table in (
        structure_items,
        financial_reports,
        risk_factors,
        arbitration,
        legal_events,
        procurements,
    ):
        targets = {
            element.target_fullname
            for constraint in table.foreign_key_constraints
            for element in constraint.elements
        }
        assert targets == {
            "company_reports.report_id",
            "company_reports.inn",
        }
