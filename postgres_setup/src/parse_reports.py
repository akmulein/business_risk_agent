from __future__ import annotations

import argparse
import json
import uuid
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def get_in(obj: dict[str, Any] | None, *keys: str, default=None):
    """Safe nested dict access."""
    cur: Any = obj
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def unwrap_date(value: Any) -> str | None:
    """Preserve source timestamp/date as ISO-like string without timezone shifts."""
    if value is None:
        return None
    if isinstance(value, dict) and "$date" in value:
        return str(value["$date"])
    return str(value)


def unwrap_number(value: Any) -> Decimal | None:
    """Parse normal numbers, Mongo $numberLong values, and numeric strings."""
    if value is None or value == "":
        return None
    if isinstance(value, dict):
        if "$numberLong" in value:
            value = value["$numberLong"]
        elif "$numberDecimal" in value:
            value = value["$numberDecimal"]
        else:
            return None
    if isinstance(value, bool):
        return Decimal(int(value))
    try:
        return Decimal(str(value).replace(" ", "").replace(",", "."))
    except (InvalidOperation, ValueError):
        return None


def json_text(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def make_report_id(inn: str, report_date: str | None) -> str:
    """Stable UUID for the same company snapshot."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"counterparty:{inn}:{report_date}"))


def ensure_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def as_text(value: Any) -> str | None:
    """Return identifiers/codes as text, preserving leading zeroes."""
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


# -----------------------------------------------------------------------------
# Main parser
# -----------------------------------------------------------------------------

def parse_reports(raw: list[dict[str, Any]]) -> dict[str, pd.DataFrame]:
    company_reports: list[dict[str, Any]] = []
    structure_items: list[dict[str, Any]] = []
    financial_reports: list[dict[str, Any]] = []
    risk_factors: list[dict[str, Any]] = []
    arbitration: list[dict[str, Any]] = []
    legal_events: list[dict[str, Any]] = []
    procurements: list[dict[str, Any]] = []

    for root in raw:
        report = root.get("report") or {}
        base = report.get("baseInfo") or {}

        inn = str(base.get("inn") or "").strip()
        if not inn:
            raise ValueError("Report without baseInfo.inn found")

        report_date = unwrap_date(report.get("reportDate"))
        report_id = make_report_id(inn, report_date)

        registration = base.get("registrationInfo") or {}
        status = report.get("status") or {}
        founders = report.get("foundersInfo") or {}

        company_reports.append(
            {
                "report_id": report_id,
                "report_date": report_date,
                "inn": inn,
                "ogrn": as_text(base.get("ogrn")),
                "short_name": base.get("shortName"),
                "full_name": base.get("fullName"),
                "risk_level": base.get("riskLevel"),
                "zsk_risk_level": report.get("zskRiskLevel"),
                "kpp": as_text(base.get("kpp")),
                "okpo": as_text(base.get("okpo")),
                "address": base.get("address"),
                "email": base.get("email"),
                "website": base.get("website"),
                "company_size": base.get("companySize"),
                "staff": base.get("staff"),  # in spec, absent in current snapshot
                "registration_date": unwrap_date(registration.get("registrationDate")),
                "years_from_registration": registration.get("yearsFromRegistration"),
                "status": status.get("status"),
                "status_reason": status.get("reasonName"),
                "status_date": unwrap_date(status.get("date")),
                "share_capital": unwrap_number(founders.get("shareCapital")),
                "branches_count": (report.get("branchesInfo") or {}).get("branchesCount"),
                # Full source report is kept losslessly as source of truth.
                "raw_report_json": json_text(report),
            }
        )

        # ------------------------------------------------------------------
        # STRUCTURE ITEMS
        # founder / director / parent org / related company / activity /
        # branch / phone / tax system
        # ------------------------------------------------------------------
        for idx, founder in enumerate(ensure_list(founders.get("cofounders"))):
            if not isinstance(founder, dict):
                continue
            structure_items.append(
                {
                    "report_id": report_id,
                    "company_inn": inn,
                    "subject_inn": inn,
                    "item_type": "founder",
                    "item_index": idx,
                    "name": founder.get("name"),
                    "related_inn": as_text(founder.get("inn")),
                    "related_ogrn": None,
                    "role": "founder",
                    "position": None,
                    "code": None,
                    "description": None,
                    "share": unwrap_number(founder.get("share")),
                    "amount": unwrap_number(founder.get("amount")),
                    "date_from": unwrap_date(founder.get("dateFrom")),
                    "active": founder.get("active", founder.get("isActive")),
                    "registration_date": None,
                    "address": None,
                    "phone_type": None,
                    "phone_code": None,
                    "phone_number": None,
                    "auth_person_name": None,
                    "auth_person_position": None,
                    "details_json": json_text(founder),
                }
            )

        auth = founders.get("authPerson") or {}
        if auth:
            structure_items.append(
                {
                    "report_id": report_id,
                    "company_inn": inn,
                    "subject_inn": inn,
                    "item_type": "director",
                    "item_index": 0,
                    "name": auth.get("name"),
                    "related_inn": as_text(auth.get("inn")),
                    "related_ogrn": None,
                    "role": "director",
                    "position": auth.get("positionName"),
                    "code": None,
                    "description": None,
                    "share": None,
                    "amount": None,
                    "date_from": unwrap_date(auth.get("positionDate")),
                    "active": None,
                    "registration_date": None,
                    "address": None,
                    "phone_type": None,
                    "phone_code": None,
                    "phone_number": None,
                    "auth_person_name": None,
                    "auth_person_position": None,
                    "details_json": json_text(auth),
                }
            )

        for idx, parent in enumerate(ensure_list(founders.get("parentOrganizations"))):
            if not isinstance(parent, dict):
                continue
            structure_items.append(
                {
                    "report_id": report_id,
                    "company_inn": inn,
                    "subject_inn": inn,
                    "item_type": "parent_organization",
                    "item_index": idx,
                    "name": parent.get("fullName"),
                    "related_inn": as_text(parent.get("inn")),
                    "related_ogrn": as_text(parent.get("ogrn")),
                    "role": "parent_organization",
                    "position": None,
                    "code": None,
                    "description": None,
                    "share": None,
                    "amount": None,
                    "date_from": unwrap_date(parent.get("parentDate")),
                    "active": None,
                    "registration_date": None,
                    "address": None,
                    "phone_type": None,
                    "phone_code": None,
                    "phone_number": None,
                    "auth_person_name": None,
                    "auth_person_position": None,
                    "details_json": json_text(parent),
                }
            )

        for idx, related in enumerate(ensure_list(report.get("relatedCompanies"))):
            if not isinstance(related, dict):
                continue
            structure_items.append(
                {
                    "report_id": report_id,
                    "company_inn": inn,
                    "subject_inn": inn,
                    "item_type": "related_company",
                    "item_index": idx,
                    "name": related.get("name"),
                    "related_inn": as_text(related.get("inn")),
                    "related_ogrn": as_text(related.get("ogrn")),
                    "role": "related_company",
                    "position": None,
                    "code": None,
                    "description": None,
                    "share": None,
                    "amount": None,
                    "date_from": None,
                    "active": None,
                    "registration_date": unwrap_date(related.get("registrationDate")),
                    "address": None,
                    "phone_type": None,
                    "phone_code": None,
                    "phone_number": None,
                    "auth_person_name": related.get("authPersonName"),
                    "auth_person_position": related.get("authPersonPosition"),
                    # nested parentOrganizations of related company remain lossless here
                    "details_json": json_text(related),
                }
            )

            # A related company may itself have a managing/parent organization.
            # Store it as its own row so structure tools do not need to parse nested JSON.
            for parent_idx, related_parent in enumerate(ensure_list(related.get("parentOrganizations"))):
                if not isinstance(related_parent, dict):
                    continue
                structure_items.append(
                    {
                        "report_id": report_id,
                        "company_inn": inn,
                        # The subject is the related company whose parent is described here.
                        "subject_inn": as_text(related.get("inn")),
                        "item_type": "related_parent_organization",
                        "item_index": parent_idx,
                        "name": related_parent.get("fullName"),
                        "related_inn": as_text(related_parent.get("inn")),
                        "related_ogrn": as_text(related_parent.get("ogrn")),
                        "role": "parent_of_related_company",
                        "position": None,
                        "code": None,
                        "description": None,
                        "share": None,
                        "amount": None,
                        "date_from": unwrap_date(related_parent.get("parentDate")),
                        "active": None,
                        "registration_date": None,
                        "address": None,
                        "phone_type": None,
                        "phone_code": None,
                        "phone_number": None,
                        "auth_person_name": None,
                        "auth_person_position": None,
                        "details_json": json_text(related_parent),
                    }
                )

        activities = report.get("kindsOfActivityInfo") or {}
        main_activity = activities.get("mainKindOfActivity") or {}
        if main_activity:
            structure_items.append(
                {
                    "report_id": report_id,
                    "company_inn": inn,
                    "subject_inn": inn,
                    "item_type": "activity",
                    "item_index": 0,
                    "name": None,
                    "related_inn": None,
                    "related_ogrn": None,
                    "role": "main",
                    "position": None,
                    "code": as_text(main_activity.get("code")),
                    "description": main_activity.get("description"),
                    "share": None,
                    "amount": None,
                    "date_from": None,
                    "active": None,
                    "registration_date": None,
                    "address": None,
                    "phone_type": None,
                    "phone_code": None,
                    "phone_number": None,
                    "auth_person_name": None,
                    "auth_person_position": None,
                    "details_json": json_text(main_activity),
                }
            )
        for idx, activity in enumerate(ensure_list(activities.get("otherKindsOfActivity")), start=1):
            if not isinstance(activity, dict):
                continue
            structure_items.append(
                {
                    "report_id": report_id,
                    "company_inn": inn,
                    "subject_inn": inn,
                    "item_type": "activity",
                    "item_index": idx,
                    "name": None,
                    "related_inn": None,
                    "related_ogrn": None,
                    "role": "other",
                    "position": None,
                    "code": as_text(activity.get("code")),
                    "description": activity.get("description"),
                    "share": None,
                    "amount": None,
                    "date_from": None,
                    "active": None,
                    "registration_date": None,
                    "address": None,
                    "phone_type": None,
                    "phone_code": None,
                    "phone_number": None,
                    "auth_person_name": None,
                    "auth_person_position": None,
                    "details_json": json_text(activity),
                }
            )

        branches = report.get("branchesInfo") or {}
        for idx, branch in enumerate(ensure_list(branches.get("branches"))):
            if not isinstance(branch, dict):
                continue
            structure_items.append(
                {
                    "report_id": report_id,
                    "company_inn": inn,
                    "subject_inn": inn,
                    "item_type": "branch",
                    "item_index": idx,
                    "name": branch.get("name"),
                    "related_inn": None,
                    "related_ogrn": None,
                    "role": "branch",
                    "position": None,
                    "code": None,
                    "description": None,
                    "share": None,
                    "amount": None,
                    "date_from": None,
                    "active": None,
                    "registration_date": None,
                    "address": branch.get("address"),
                    "phone_type": None,
                    "phone_code": None,
                    "phone_number": None,
                    "auth_person_name": None,
                    "auth_person_position": None,
                    "details_json": json_text(branch),
                }
            )

        for idx, phone in enumerate(ensure_list(report.get("phones"))):
            if not isinstance(phone, dict):
                continue
            structure_items.append(
                {
                    "report_id": report_id,
                    "company_inn": inn,
                    "subject_inn": inn,
                    "item_type": "phone",
                    "item_index": idx,
                    "name": None,
                    "related_inn": None,
                    "related_ogrn": None,
                    "role": "phone",
                    "position": None,
                    "code": None,
                    "description": None,
                    "share": None,
                    "amount": None,
                    "date_from": None,
                    "active": None,
                    "registration_date": None,
                    "address": None,
                    "phone_type": phone.get("phoneType"),
                    "phone_code": as_text(phone.get("phoneCode")),
                    "phone_number": as_text(phone.get("phoneNumber")),
                    "auth_person_name": None,
                    "auth_person_position": None,
                    "details_json": json_text(phone),
                }
            )

        for idx, tax in enumerate(ensure_list(report.get("taxSystem"))):
            if not isinstance(tax, dict):
                continue
            structure_items.append(
                {
                    "report_id": report_id,
                    "company_inn": inn,
                    "subject_inn": inn,
                    "item_type": "tax_system",
                    "item_index": idx,
                    "name": tax.get("fullName"),
                    "related_inn": None,
                    "related_ogrn": None,
                    "role": "tax_system",
                    "position": None,
                    "code": as_text(tax.get("shortName")),
                    "description": None,
                    "share": None,
                    "amount": None,
                    "date_from": None,
                    "active": None,
                    "registration_date": None,
                    "address": None,
                    "phone_type": None,
                    "phone_code": None,
                    "phone_number": None,
                    "auth_person_name": None,
                    "auth_person_position": None,
                    "details_json": json_text(tax),
                }
            )

        # ------------------------------------------------------------------
        # FINANCIAL REPORTS (company x year)
        # ------------------------------------------------------------------
        coeff_by_year: dict[int, dict[str, Any]] = {}
        for coeff in ensure_list(report.get("coefficient")):
            if isinstance(coeff, dict) and coeff.get("year") is not None:
                coeff_by_year[int(coeff["year"])] = coeff

        for fin in ensure_list(report.get("finReports")):
            if not isinstance(fin, dict):
                continue
            common = fin.get("common") or {}
            assets = fin.get("assets") or {}
            current = assets.get("currentAssets") or {}
            uncurrent = assets.get("uncurrentAssets") or {}
            liabilities = fin.get("liabilities") or {}
            long_term = liabilities.get("longTermDuties") or {}
            short_term = liabilities.get("shortTermLiabilities") or {}
            year = common.get("year")
            coeff = coeff_by_year.get(int(year)) if year is not None else {}

            financial_reports.append(
                {
                    "report_id": report_id,
                    "company_inn": inn,
                    "year": year,
                    "proceeds": unwrap_number(common.get("proceeds")),
                    "profit": unwrap_number(common.get("profit")),
                    "total_assets": unwrap_number(assets.get("totalAssets")),
                    "current_assets_total": unwrap_number(current.get("total")),
                    "stocks": unwrap_number(current.get("stocks")),
                    "receivables": unwrap_number(current.get("receivables")),
                    "bankroll": unwrap_number(current.get("bankroll")),
                    "uncurrent_assets_total": unwrap_number(uncurrent.get("total")),
                    "fixed_assets": unwrap_number(uncurrent.get("fixedAssets")),
                    "total_liabilities": unwrap_number(liabilities.get("totalLiabilities")),
                    "capitals": unwrap_number(liabilities.get("capitals")),
                    "long_term_duties_total": unwrap_number(long_term.get("total")),
                    "long_term_duties_others": unwrap_number(long_term.get("others")),
                    "short_term_liabilities_total": unwrap_number(short_term.get("total")),
                    "borrowed_funds": unwrap_number(short_term.get("borrowedFunds")),
                    "accounts_payable": unwrap_number(short_term.get("accountsPayable")),
                    "sustainability": unwrap_number((coeff or {}).get("sustainability")),
                    "solvency": unwrap_number((coeff or {}).get("solvency")),
                    "profitability": unwrap_number((coeff or {}).get("profitability")),
                }
            )

        # If coefficient exists for a year absent from finReports, do not lose it.
        existing_years = {row["year"] for row in financial_reports if row["report_id"] == report_id}
        for year, coeff in coeff_by_year.items():
            if year in existing_years:
                continue
            financial_reports.append(
                {
                    "report_id": report_id,
                    "company_inn": inn,
                    "year": year,
                    "proceeds": None,
                    "profit": None,
                    "total_assets": None,
                    "current_assets_total": None,
                    "stocks": None,
                    "receivables": None,
                    "bankroll": None,
                    "uncurrent_assets_total": None,
                    "fixed_assets": None,
                    "total_liabilities": None,
                    "capitals": None,
                    "long_term_duties_total": None,
                    "long_term_duties_others": None,
                    "short_term_liabilities_total": None,
                    "borrowed_funds": None,
                    "accounts_payable": None,
                    "sustainability": unwrap_number(coeff.get("sustainability")),
                    "solvency": unwrap_number(coeff.get("solvency")),
                    "profitability": unwrap_number(coeff.get("profitability")),
                }
            )

        # ------------------------------------------------------------------
        # REPUTATIONAL RISK FACTORS
        # ------------------------------------------------------------------
        rep_risks = report.get("reputationalRisks") or {}
        for sign in ("negative", "positive"):
            for idx, factor in enumerate(ensure_list(rep_risks.get(sign))):
                if not isinstance(factor, dict):
                    continue
                risk_factors.append(
                    {
                        "report_id": report_id,
                        "company_inn": inn,
                        "sign": sign,
                        "item_index": idx,
                        "code": factor.get("code"),
                        "name": factor.get("name"),
                        "chapter": factor.get("chapter"),
                    }
                )

        # ------------------------------------------------------------------
        # ARBITRATION
        # One generic row format: source, role, case_status, count, amount.
        # ------------------------------------------------------------------
        for case in ensure_list(report.get("arbitrationCases")):
            if not isinstance(case, dict):
                continue
            year = case.get("year")
            arbitration.extend(
                [
                    {
                        "report_id": report_id,
                        "company_inn": inn,
                        "source": "yearly",
                        "year": year,
                        "role": "plaintiff",
                        "case_status": "all",
                        "case_count": unwrap_number(case.get("plaintiffCount")),
                        "amount": unwrap_number(case.get("plaintiffAmount")),
                    },
                    {
                        "report_id": report_id,
                        "company_inn": inn,
                        "source": "yearly",
                        "year": year,
                        "role": "defendant",
                        "case_status": "all",
                        "case_count": unwrap_number(case.get("defendantCount")),
                        "amount": unwrap_number(case.get("defendantAmount")),
                    },
                ]
            )

        by_status = report.get("arbitrationByStatus") or {}
        if "commonCount" in by_status or "commonAmount" in by_status:
            arbitration.append(
                {
                    "report_id": report_id,
                    "company_inn": inn,
                    "source": "status",
                    "year": None,
                    "role": "all",
                    "case_status": "all",
                    "case_count": unwrap_number(by_status.get("commonCount")),
                    "amount": unwrap_number(by_status.get("commonAmount")),
                }
            )

        status_mapping = [
            ("plaintiff", "finished", "plaintiffArbitration", "plaintiffArbitrationFinished", "pfCount", "pfAmount"),
            ("plaintiff", "appealed", "plaintiffArbitration", "plaintiffArbitrationAppealed", "paCount", "paAmount"),
            ("plaintiff", "pending", "plaintiffArbitration", "plaintiffArbitrationPending", "ppCount", "ppAmount"),
            ("defendant", "finished", "defandantArbitration", "defandantArbitrationFinished", "dfCount", "dfAmount"),
            ("defendant", "appealed", "defandantArbitration", "defandantArbitrationAppealed", "daCount", "daAmount"),
            ("defendant", "pending", "defandantArbitration", "defandantArbitrationPending", "dpCount", "dpAmount"),
        ]
        for role, case_status, side_key, status_key, count_key, amount_key in status_mapping:
            block = get_in(by_status, side_key, status_key, default={}) or {}
            if block:  # keep only explicit values; raw report remains available if fields are absent
                arbitration.append(
                    {
                        "report_id": report_id,
                        "company_inn": inn,
                        "source": "status",
                        "year": None,
                        "role": role,
                        "case_status": case_status,
                        "case_count": unwrap_number(block.get(count_key)),
                        "amount": unwrap_number(block.get(amount_key)),
                    }
                )

        # ------------------------------------------------------------------
        # LEGAL EVENTS: execution / inspection / license
        # ------------------------------------------------------------------
        for idx, event in enumerate(ensure_list(report.get("executionProceedings"))):
            if not isinstance(event, dict):
                continue
            legal_events.append(
                {
                    "report_id": report_id,
                    "company_inn": inn,
                    "event_type": "execution",
                    "item_index": idx,
                    "external_id": as_text(event.get("number")),
                    "event_date": unwrap_date(event.get("date")),
                    "end_date": None,
                    "active": event.get("active"),
                    "status": None,
                    "amount": unwrap_number(event.get("amount")),
                    "title": None,
                    "authority": None,
                    "form": None,
                    "details_json": json_text(event),
                }
            )

        for idx, event in enumerate(ensure_list(report.get("inspections"))):
            if not isinstance(event, dict):
                continue
            legal_events.append(
                {
                    "report_id": report_id,
                    "company_inn": inn,
                    "event_type": "inspection",
                    "item_index": idx,
                    "external_id": as_text(event.get("erpId")),
                    "event_date": unwrap_date(event.get("startDate")),
                    "end_date": unwrap_date(event.get("endDate")),
                    "active": None,
                    "status": event.get("inspectionStatus"),
                    "amount": None,
                    "title": event.get("type"),
                    "authority": event.get("authorityName"),
                    "form": event.get("form"),
                    "details_json": json_text(event),
                }
            )

        for idx, event in enumerate(ensure_list(report.get("licenses"))):
            if not isinstance(event, dict):
                continue
            legal_events.append(
                {
                    "report_id": report_id,
                    "company_inn": inn,
                    "event_type": "license",
                    "item_index": idx,
                    "external_id": as_text(event.get("number")),
                    "event_date": unwrap_date(event.get("issueDate")),
                    "end_date": unwrap_date(event.get("endDate")),
                    "active": None,
                    "status": event.get("status"),
                    "amount": None,
                    "title": event.get("name"),
                    "authority": event.get("issuingAuthority"),
                    "form": None,
                    "details_json": json_text(event),
                }
            )

        # ------------------------------------------------------------------
        # PROCUREMENTS
        # ------------------------------------------------------------------
        for idx, item in enumerate(ensure_list(report.get("procurements"))):
            if not isinstance(item, dict):
                continue
            procurements.append(
                {
                    "report_id": report_id,
                    "company_inn": inn,
                    "item_index": idx,
                    "year": item.get("procurementsYear"),
                    "federal_law_code": as_text(item.get("federalLawCode")),
                    "tender_admitted_count": unwrap_number(item.get("tenderAdmittedCnt")),
                    "tender_winner_count": unwrap_number(item.get("tenderWinnerCnt")),
                    "contract_signed_count": unwrap_number(item.get("contractSignedCnt")),
                    "contract_signed_amount": unwrap_number(item.get("contractSignedAmt")),
                }
            )

    tables = {
        "company_reports": pd.DataFrame(company_reports),
        "structure_items": pd.DataFrame(structure_items),
        "financial_reports": pd.DataFrame(financial_reports),
        "risk_factors": pd.DataFrame(risk_factors),
        "arbitration": pd.DataFrame(arbitration),
        "legal_events": pd.DataFrame(legal_events),
        "procurements": pd.DataFrame(procurements),
    }

    # Identifiers are not numbers. Keep them as pandas StringDtype so leading
    # zeroes survive parsing and direct loading into PostgreSQL TEXT columns.
    text_columns = {
        "company_reports": ["report_id", "inn", "ogrn", "kpp", "okpo"],
        "structure_items": [
            "report_id", "company_inn", "subject_inn", "related_inn",
            "related_ogrn", "code", "phone_code", "phone_number"
        ],
        "financial_reports": ["report_id", "company_inn"],
        "risk_factors": ["report_id", "company_inn", "code", "chapter"],
        "arbitration": ["report_id", "company_inn"],
        "legal_events": ["report_id", "company_inn", "external_id"],
        "procurements": ["report_id", "company_inn", "federal_law_code"],
    }
    for table_name, columns in text_columns.items():
        df = tables[table_name]
        for column in columns:
            if column in df.columns:
                df[column] = df[column].astype("string")

    # Keep nullable integer fields as true integers when writing CSV.
    # Without this, pandas may serialize values like 1 and 2023 as 1.0 / 2023.0
    # whenever the column also contains missing values, which PostgreSQL INTEGER
    # and SMALLINT columns reject during COPY.
    integer_columns = {
        "company_reports": ["years_from_registration", "branches_count"],
        "structure_items": ["item_index"],
        "financial_reports": ["year"],
        "risk_factors": ["item_index"],
        "arbitration": ["year", "case_count"],
        "legal_events": ["item_index"],
        "procurements": [
            "item_index", "year", "tender_admitted_count",
            "tender_winner_count", "contract_signed_count"
        ],
    }
    for table_name, columns in integer_columns.items():
        df = tables[table_name]
        for column in columns:
            if column in df.columns:
                df[column] = pd.to_numeric(df[column], errors="coerce").astype("Int64")

    return tables


# -----------------------------------------------------------------------------
# Validation + CLI
# -----------------------------------------------------------------------------

def validate_tables(tables: dict[str, pd.DataFrame], source_count: int) -> None:
    companies = tables["company_reports"]

    if len(companies) != source_count:
        raise AssertionError(
            f"company_reports rows={len(companies)} but source reports={source_count}"
        )

    if companies["report_id"].duplicated().any():
        dupes = companies.loc[companies["report_id"].duplicated(), "report_id"].tolist()
        raise AssertionError(f"Duplicate report_id values: {dupes[:5]}")

    if companies["inn"].isna().any() or (companies["inn"].astype(str).str.len() == 0).any():
        raise AssertionError("Empty INN found")

    report_ids = set(companies["report_id"])
    for name, df in tables.items():
        if name == "company_reports" or df.empty:
            continue
        unknown = set(df["report_id"]) - report_ids
        if unknown:
            raise AssertionError(f"{name}: rows reference unknown report_id")


def save_tables(tables: dict[str, pd.DataFrame], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_csv(output_dir / f"{name}.csv", index=False, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse contractor audit JSON into 7 canonical tables")
    parser.add_argument("input_json", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("data/processed"))
    args = parser.parse_args()

    with args.input_json.open("r", encoding="utf-8") as f:
        raw = json.load(f)

    if not isinstance(raw, list):
        raise TypeError("Expected top-level JSON array")

    tables = parse_reports(raw)
    validate_tables(tables, source_count=len(raw))
    save_tables(tables, args.output_dir)

    print(f"Parsed {len(raw)} reports")
    for name, df in tables.items():
        print(f"{name:20s}: {len(df):5d} rows x {len(df.columns):2d} columns")
    print(f"Saved to: {args.output_dir.resolve()}")


if __name__ == "__main__":
    main()
