from __future__ import annotations

import argparse
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from psycopg import sql


TABLES = {
    "company_reports": [
        "report_id", "report_date", "inn", "ogrn", "short_name", "full_name",
        "risk_level", "zsk_risk_level", "kpp", "okpo", "address", "email",
        "website", "company_size", "staff", "registration_date",
        "years_from_registration", "status", "status_reason", "status_date",
        "share_capital", "branches_count", "raw_report_json",
    ],
    "structure_items": [
        "report_id", "company_inn", "subject_inn", "item_type", "item_index",
        "name", "related_inn", "related_ogrn", "role", "position", "code",
        "description", "share", "amount", "date_from", "active",
        "registration_date", "address", "phone_type", "phone_code",
        "phone_number", "auth_person_name", "auth_person_position", "details_json",
    ],
    "financial_reports": [
        "report_id", "company_inn", "year", "proceeds", "profit", "total_assets",
        "current_assets_total", "stocks", "receivables", "bankroll",
        "uncurrent_assets_total", "fixed_assets", "total_liabilities", "capitals",
        "long_term_duties_total", "long_term_duties_others",
        "short_term_liabilities_total", "borrowed_funds", "accounts_payable",
        "sustainability", "solvency", "profitability",
    ],
    "risk_factors": [
        "report_id", "company_inn", "sign", "item_index", "code", "name", "chapter",
    ],
    "arbitration": [
        "report_id", "company_inn", "source", "year", "role", "case_status",
        "case_count", "amount",
    ],
    "legal_events": [
        "report_id", "company_inn", "event_type", "item_index", "external_id",
        "event_date", "end_date", "active", "status", "amount", "title",
        "authority", "form", "details_json",
    ],
    "procurements": [
        "report_id", "company_inn", "item_index", "year", "federal_law_code",
        "tender_admitted_count", "tender_winner_count", "contract_signed_count",
        "contract_signed_amount",
    ],
}


def get_connection() -> psycopg.Connection:
    database_url = os.getenv("DATABASE_URL")

    if database_url:
        return psycopg.connect(database_url)

    return psycopg.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=os.getenv("POSTGRES_DB", "contractors"),
        user=os.getenv("POSTGRES_USER", "contractors_user"),
        password=os.getenv("POSTGRES_PASSWORD"),
    )


def copy_csv(cur: psycopg.Cursor, table: str, columns: list[str], csv_path: Path) -> None:
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    copy_stmt = sql.SQL(
        "COPY {} ({}) FROM STDIN WITH (FORMAT CSV, HEADER TRUE, NULL '')"
    ).format(
        sql.Identifier(table),
        sql.SQL(", ").join(map(sql.Identifier, columns)),
    )

    with csv_path.open("r", encoding="utf-8", newline="") as f:
        with cur.copy(copy_stmt) as copy:
            while chunk := f.read(1024 * 1024):
                copy.write(chunk)


def main() -> None:
    parser = argparse.ArgumentParser(description="Load parsed contractor CSVs into PostgreSQL")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data/processed"),
        help="Directory containing the seven parsed CSV files",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append instead of clearing existing data first",
    )
    args = parser.parse_args()

    load_dotenv()

    if not os.getenv("POSTGRES_PASSWORD"):
        raise RuntimeError("POSTGRES_PASSWORD is not set. Create .env from .env.example")

    with get_connection() as conn:
        with conn.cursor() as cur:
            if not args.append:
                cur.execute(
                    """
                    TRUNCATE TABLE
                        structure_items,
                        financial_reports,
                        risk_factors,
                        arbitration,
                        legal_events,
                        procurements,
                        company_reports
                    RESTART IDENTITY CASCADE
                    """
                )

            for table, columns in TABLES.items():
                csv_path = args.data_dir / f"{table}.csv"
                print(f"Loading {csv_path} -> {table} ...")
                copy_csv(cur, table, columns, csv_path)

            conn.commit()

            print("\nLoaded row counts:")
            for table in TABLES:
                cur.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(table)))
                count = cur.fetchone()[0]
                print(f"  {table:20s} {count}")

            # Lightweight referential sanity check.
            cur.execute(
                """
                SELECT COUNT(*)
                FROM legal_events le
                LEFT JOIN company_reports cr
                  ON cr.report_id = le.report_id AND cr.inn = le.company_inn
                WHERE cr.report_id IS NULL
                """
            )
            broken = cur.fetchone()[0]
            if broken:
                raise RuntimeError(f"Found {broken} broken legal_events references")

    print("\nDatabase load completed successfully.")


if __name__ == "__main__":
    main()
