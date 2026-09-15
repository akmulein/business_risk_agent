"""Проверка соответствия данных из Mongo исходному json-отчёту"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any



_INDEXED_PATH = re.compile(r"^(?P<section>\w+)\[(?P<index>\d+)]\.(?P<field>\w+)$")
_RISK_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "UNKNOWN": 3}
_FNS_CODES = {
    "taxArrears",
    "taxReporting",
    "fnsBlocking",
    "invalidRegistrationData",
    "invalidAddress",
    "massAddress",
}


def _object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _array(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _scalar(value: Any) -> Any:
    if isinstance(value, dict) and len(value) == 1:
        key, inner = next(iter(value.items()))
        if key == "$date":
            return inner
        if key in {"$numberLong", "$numberInt"}:
            return int(inner)
        if key in {"$numberDouble", "$numberDecimal"}:
            return Decimal(str(inner))
    return value


def _text(value: Any) -> str | None:
    value = _scalar(value)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _number(value: Any) -> Any:
    value = _scalar(value)
    return None if value in (None, "") else value


def _canonical(value: Any) -> Any:
    value = _scalar(value)
    if isinstance(value, list):
        return [_canonical(item) for item in value]
    if isinstance(value, dict):
        return {key: _canonical(item) for key, item in value.items()}
    if type(value) in (int, float, Decimal):
        return Decimal(str(value))
    if isinstance(value, str) and re.fullmatch(r"[+-]?\d+(?:\.\d+)?", value):
        return Decimal(value)
    if isinstance(value, str) and re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z", value
    ):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc).isoformat()
    return value


def _equal(expected: Any, actual: Any) -> bool:
    return _canonical(expected) == _canonical(actual)


class Projection:
    def __init__(self) -> None:
        self.card: dict[str, Any] = {
            "company_reports": {},
            "structure_items": [],
            "financial_reports": [],
            "risk_factors": [],
            "arbitration": [],
            "legal_events": [],
            "procurements": [],
        }
        self.paths: dict[str, str] = {}

    def company(self, field: str, value: Any, raw_path: str) -> None:
        self.card["company_reports"][field] = value
        self.paths[f"company_reports.{field}"] = raw_path

    def item(
        self,
        section: str,
        values: dict[str, tuple[Any, str]],
    ) -> None:
        index = len(self.card[section])
        item: dict[str, Any] = {}
        for field, (value, raw_path) in values.items():
            item[field] = value
            self.paths[f"{section}[{index}].{field}"] = raw_path
        self.card[section].append(item)


def project_raw_report(report: dict[str, Any]) -> Projection:
    """Build expected normalized values directly from raw source fields."""
    result = Projection()
    base = _object(report.get("baseInfo"))
    registration = _object(base.get("registrationInfo"))
    status = _object(report.get("status"))
    founders = _object(report.get("foundersInfo"))
    branches = _object(report.get("branchesInfo"))
    report_date = _scalar(report.get("reportDate"))
    inn = _text(base.get("inn"))
    report_id = f"{inn}:{report_date or 'undated'}"
    company_fields = {
        "report_id": (report_id, "report.reportDate + report.baseInfo.inn"),
        "report_date": (report_date, "report.reportDate"),
        "inn": (inn, "report.baseInfo.inn"),
        "ogrn": (_text(base.get("ogrn")), "report.baseInfo.ogrn"),
        "short_name": (base.get("shortName"), "report.baseInfo.shortName"),
        "full_name": (base.get("fullName"), "report.baseInfo.fullName"),
        "risk_level": (base.get("riskLevel"), "report.baseInfo.riskLevel"),
        "zsk_risk_level": (report.get("zskRiskLevel"), "report.zskRiskLevel"),
        "kpp": (_text(base.get("kpp")), "report.baseInfo.kpp"),
        "okpo": (_text(base.get("okpo")), "report.baseInfo.okpo"),
        "address": (base.get("address"), "report.baseInfo.address"),
        "email": (base.get("email"), "report.baseInfo.email"),
        "website": (base.get("website"), "report.baseInfo.website"),
        "company_size": (base.get("companySize"), "report.baseInfo.companySize"),
        "staff": (base.get("staff"), "report.baseInfo.staff"),
        "registration_date": (
            _scalar(registration.get("registrationDate")),
            "report.baseInfo.registrationInfo.registrationDate",
        ),
        "years_from_registration": (
            registration.get("yearsFromRegistration"),
            "report.baseInfo.registrationInfo.yearsFromRegistration",
        ),
        "status": (status.get("status"), "report.status.status"),
        "status_reason": (status.get("reasonName"), "report.status.reasonName"),
        "status_date": (_scalar(status.get("date")), "report.status.date"),
        "share_capital": (
            _number(founders.get("shareCapital")),
            "report.foundersInfo.shareCapital",
        ),
        "branches_count": (
            branches.get("branchesCount"),
            "report.branchesInfo.branchesCount",
        ),
    }
    for field, (value, raw_path) in company_fields.items():
        result.company(field, value, raw_path)

    for index, value in enumerate(_array(founders.get("cofounders"))):
        item = _object(value)
        prefix = f"report.foundersInfo.cofounders[{index}]"
        result.item(
            "structure_items",
            {
                "item_type": ("founder", prefix),
                "item_index": (index, prefix),
                "name": (item.get("name"), f"{prefix}.name"),
                "related_inn": (_text(item.get("inn")), f"{prefix}.inn"),
                "role": ("founder", prefix),
                "share": (_number(item.get("share")), f"{prefix}.share"),
                "amount": (_number(item.get("amount")), f"{prefix}.amount"),
                "date_from": (_scalar(item.get("dateFrom")), f"{prefix}.dateFrom"),
                "active": (item.get("active", item.get("isActive")), f"{prefix}.active"),
            },
        )
    auth = _object(founders.get("authPerson"))
    if auth:
        prefix = "report.foundersInfo.authPerson"
        result.item(
            "structure_items",
            {
                "item_type": ("director", prefix),
                "item_index": (0, prefix),
                "name": (auth.get("name"), f"{prefix}.name"),
                "related_inn": (_text(auth.get("inn")), f"{prefix}.inn"),
                "role": ("director", prefix),
                "position": (auth.get("positionName"), f"{prefix}.positionName"),
                "date_from": (_scalar(auth.get("positionDate")), f"{prefix}.positionDate"),
            },
        )
    for index, value in enumerate(_array(founders.get("parentOrganizations"))):
        item = _object(value)
        prefix = f"report.foundersInfo.parentOrganizations[{index}]"
        result.item(
            "structure_items",
            {
                "item_type": ("parent_organization", prefix),
                "item_index": (index, prefix),
                "name": (item.get("fullName"), f"{prefix}.fullName"),
                "related_inn": (_text(item.get("inn")), f"{prefix}.inn"),
                "related_ogrn": (_text(item.get("ogrn")), f"{prefix}.ogrn"),
                "role": ("parent_organization", prefix),
                "date_from": (_scalar(item.get("parentDate")), f"{prefix}.parentDate"),
            },
        )
    for index, value in enumerate(_array(report.get("relatedCompanies"))):
        item = _object(value)
        prefix = f"report.relatedCompanies[{index}]"
        related_inn = _text(item.get("inn"))
        result.item(
            "structure_items",
            {
                "item_type": ("related_company", prefix),
                "item_index": (index, prefix),
                "name": (item.get("name"), f"{prefix}.name"),
                "related_inn": (related_inn, f"{prefix}.inn"),
                "related_ogrn": (_text(item.get("ogrn")), f"{prefix}.ogrn"),
                "role": ("related_company", prefix),
                "registration_date": (_scalar(item.get("registrationDate")), f"{prefix}.registrationDate"),
                "auth_person_name": (item.get("authPersonName"), f"{prefix}.authPersonName"),
                "auth_person_position": (item.get("authPersonPosition"), f"{prefix}.authPersonPosition"),
            },
        )
        for parent_index, parent_value in enumerate(_array(item.get("parentOrganizations"))):
            parent = _object(parent_value)
            parent_prefix = f"{prefix}.parentOrganizations[{parent_index}]"
            result.item(
                "structure_items",
                {
                    "item_type": ("related_parent_organization", parent_prefix),
                    "item_index": (parent_index, parent_prefix),
                    "name": (parent.get("fullName"), f"{parent_prefix}.fullName"),
                    "related_inn": (_text(parent.get("inn")), f"{parent_prefix}.inn"),
                    "related_ogrn": (_text(parent.get("ogrn")), f"{parent_prefix}.ogrn"),
                    "role": ("parent_of_related_company", parent_prefix),
                    "date_from": (_scalar(parent.get("parentDate")), f"{parent_prefix}.parentDate"),
                },
            )
    activities = _object(report.get("kindsOfActivityInfo"))
    main_activity = _object(activities.get("mainKindOfActivity"))
    if main_activity:
        prefix = "report.kindsOfActivityInfo.mainKindOfActivity"
        result.item(
            "structure_items",
            {
                "item_type": ("activity", prefix),
                "item_index": (0, prefix),
                "role": ("main", prefix),
                "code": (_text(main_activity.get("code")), f"{prefix}.code"),
                "description": (main_activity.get("description"), f"{prefix}.description"),
            },
        )
    for offset, value in enumerate(_array(activities.get("otherKindsOfActivity"))):
        item = _object(value)
        prefix = f"report.kindsOfActivityInfo.otherKindsOfActivity[{offset}]"
        result.item(
            "structure_items",
            {
                "item_type": ("activity", prefix),
                "item_index": (offset + 1, prefix),
                "role": ("other", prefix),
                "code": (_text(item.get("code")), f"{prefix}.code"),
                "description": (item.get("description"), f"{prefix}.description"),
            },
        )
    for index, value in enumerate(_array(branches.get("branches"))):
        item = _object(value)
        prefix = f"report.branchesInfo.branches[{index}]"
        result.item(
            "structure_items",
            {
                "item_type": ("branch", prefix),
                "item_index": (index, prefix),
                "name": (item.get("name"), f"{prefix}.name"),
                "role": ("branch", prefix),
                "address": (item.get("address"), f"{prefix}.address"),
            },
        )
    for index, value in enumerate(_array(report.get("phones"))):
        item = _object(value)
        prefix = f"report.phones[{index}]"
        result.item(
            "structure_items",
            {
                "item_type": ("phone", prefix),
                "item_index": (index, prefix),
                "role": ("phone", prefix),
                "phone_type": (item.get("phoneType"), f"{prefix}.phoneType"),
                "phone_code": (_text(item.get("phoneCode")), f"{prefix}.phoneCode"),
                "phone_number": (_text(item.get("phoneNumber")), f"{prefix}.phoneNumber"),
            },
        )
    for index, value in enumerate(_array(report.get("taxSystem"))):
        item = _object(value)
        prefix = f"report.taxSystem[{index}]"
        result.item(
            "structure_items",
            {
                "item_type": ("tax_system", prefix),
                "item_index": (index, prefix),
                "name": (item.get("fullName"), f"{prefix}.fullName"),
                "role": ("tax_system", prefix),
                "code": (_text(item.get("shortName")), f"{prefix}.shortName"),
            },
        )

    coefficients: dict[int, tuple[dict[str, Any], str]] = {}
    for index, value in enumerate(_array(report.get("coefficient"))):
        item = _object(value)
        if item.get("year") is not None:
            coefficients[int(item["year"])] = (item, f"report.coefficient[{index}]")
    financial_years: set[int] = set()
    for index, value in enumerate(_array(report.get("finReports"))):
        item = _object(value)
        common = _object(item.get("common"))
        if common.get("year") is None:
            continue
        year = int(common["year"])
        financial_years.add(year)
        prefix = f"report.finReports[{index}]"
        assets = _object(item.get("assets"))
        current = _object(assets.get("currentAssets"))
        uncurrent = _object(assets.get("uncurrentAssets"))
        liabilities = _object(item.get("liabilities"))
        long_term = _object(liabilities.get("longTermDuties"))
        short_term = _object(liabilities.get("shortTermLiabilities"))
        coefficient, coefficient_prefix = coefficients.get(year, ({}, "report.coefficient"))
        result.item(
            "financial_reports",
            {
                "year": (year, f"{prefix}.common.year"),
                "proceeds": (_number(common.get("proceeds")), f"{prefix}.common.proceeds"),
                "profit": (_number(common.get("profit")), f"{prefix}.common.profit"),
                "total_assets": (_number(assets.get("totalAssets")), f"{prefix}.assets.totalAssets"),
                "current_assets_total": (_number(current.get("total")), f"{prefix}.assets.currentAssets.total"),
                "stocks": (_number(current.get("stocks")), f"{prefix}.assets.currentAssets.stocks"),
                "receivables": (_number(current.get("receivables")), f"{prefix}.assets.currentAssets.receivables"),
                "bankroll": (_number(current.get("bankroll")), f"{prefix}.assets.currentAssets.bankroll"),
                "uncurrent_assets_total": (_number(uncurrent.get("total")), f"{prefix}.assets.uncurrentAssets.total"),
                "fixed_assets": (_number(uncurrent.get("fixedAssets")), f"{prefix}.assets.uncurrentAssets.fixedAssets"),
                "total_liabilities": (_number(liabilities.get("totalLiabilities")), f"{prefix}.liabilities.totalLiabilities"),
                "capitals": (_number(liabilities.get("capitals")), f"{prefix}.liabilities.capitals"),
                "long_term_duties_total": (_number(long_term.get("total")), f"{prefix}.liabilities.longTermDuties.total"),
                "long_term_duties_others": (_number(long_term.get("others")), f"{prefix}.liabilities.longTermDuties.others"),
                "short_term_liabilities_total": (_number(short_term.get("total")), f"{prefix}.liabilities.shortTermLiabilities.total"),
                "borrowed_funds": (_number(short_term.get("borrowedFunds")), f"{prefix}.liabilities.shortTermLiabilities.borrowedFunds"),
                "accounts_payable": (_number(short_term.get("accountsPayable")), f"{prefix}.liabilities.shortTermLiabilities.accountsPayable"),
                "sustainability": (_number(coefficient.get("sustainability")), f"{coefficient_prefix}.sustainability"),
                "solvency": (_number(coefficient.get("solvency")), f"{coefficient_prefix}.solvency"),
                "profitability": (_number(coefficient.get("profitability")), f"{coefficient_prefix}.profitability"),
            },
        )
    for year, (coefficient, prefix) in coefficients.items():
        if year in financial_years:
            continue
        result.item(
            "financial_reports",
            {
                "year": (year, f"{prefix}.year"),
                "sustainability": (_number(coefficient.get("sustainability")), f"{prefix}.sustainability"),
                "solvency": (_number(coefficient.get("solvency")), f"{prefix}.solvency"),
                "profitability": (_number(coefficient.get("profitability")), f"{prefix}.profitability"),
            },
        )

    risks = _object(report.get("reputationalRisks"))
    for sign in ("negative", "positive"):
        for index, value in enumerate(_array(risks.get(sign))):
            item = _object(value)
            if not item.get("name"):
                continue
            prefix = f"report.reputationalRisks.{sign}[{index}]"
            result.item(
                "risk_factors",
                {
                    "sign": (sign, prefix),
                    "item_index": (index, prefix),
                    "code": (item.get("code"), f"{prefix}.code"),
                    "name": (item.get("name"), f"{prefix}.name"),
                    "chapter": (item.get("chapter"), f"{prefix}.chapter"),
                },
            )

    for index, value in enumerate(_array(report.get("arbitrationCases"))):
        item = _object(value)
        prefix = f"report.arbitrationCases[{index}]"
        for role, count_key, amount_key in (
            ("plaintiff", "plaintiffCount", "plaintiffAmount"),
            ("defendant", "defendantCount", "defendantAmount"),
        ):
            if item.get(count_key) is None:
                continue
            result.item(
                "arbitration",
                {
                    "source": ("yearly", prefix),
                    "year": (int(item["year"]) if item.get("year") is not None else None, f"{prefix}.year"),
                    "role": (role, prefix),
                    "case_status": ("all", prefix),
                    "case_count": (int(item[count_key]), f"{prefix}.{count_key}"),
                    "amount": (_number(item.get(amount_key)), f"{prefix}.{amount_key}"),
                },
            )
    by_status = _object(report.get("arbitrationByStatus"))
    if by_status.get("commonCount") is not None:
        result.item(
            "arbitration",
            {
                "source": ("status", "report.arbitrationByStatus"),
                "role": ("all", "report.arbitrationByStatus"),
                "case_status": ("all", "report.arbitrationByStatus"),
                "case_count": (int(by_status["commonCount"]), "report.arbitrationByStatus.commonCount"),
                "amount": (_number(by_status.get("commonAmount")), "report.arbitrationByStatus.commonAmount"),
            },
        )
    mappings = (
        ("plaintiff", "finished", "plaintiffArbitration", "plaintiffArbitrationFinished", "pfCount", "pfAmount"),
        ("plaintiff", "appealed", "plaintiffArbitration", "plaintiffArbitrationAppealed", "paCount", "paAmount"),
        ("plaintiff", "pending", "plaintiffArbitration", "plaintiffArbitrationPending", "ppCount", "ppAmount"),
        ("defendant", "finished", "defandantArbitration", "defandantArbitrationFinished", "dfCount", "dfAmount"),
        ("defendant", "appealed", "defandantArbitration", "defandantArbitrationAppealed", "daCount", "daAmount"),
        ("defendant", "pending", "defandantArbitration", "defandantArbitrationPending", "dpCount", "dpAmount"),
    )
    for role, case_status, side, status_key, count_key, amount_key in mappings:
        block = _object(_object(by_status.get(side)).get(status_key))
        if block.get(count_key) is None:
            continue
        prefix = f"report.arbitrationByStatus.{side}.{status_key}"
        result.item(
            "arbitration",
            {
                "source": ("status", prefix),
                "role": (role, prefix),
                "case_status": (case_status, prefix),
                "case_count": (int(block[count_key]), f"{prefix}.{count_key}"),
                "amount": (_number(block.get(amount_key)), f"{prefix}.{amount_key}"),
            },
        )

    event_specs = (
        ("execution", "executionProceedings", "number", "date", None),
        ("inspection", "inspections", "erpId", "startDate", "endDate"),
        ("license", "licenses", "number", "issueDate", "endDate"),
    )
    for event_type, raw_key, id_key, date_key, end_key in event_specs:
        for index, value in enumerate(_array(report.get(raw_key))):
            item = _object(value)
            prefix = f"report.{raw_key}[{index}]"
            values = {
                "event_type": (event_type, prefix),
                "item_index": (index, prefix),
                "external_id": (_text(item.get(id_key)), f"{prefix}.{id_key}"),
                "event_date": (_scalar(item.get(date_key)), f"{prefix}.{date_key}"),
            }
            if event_type == "execution":
                values.update(
                    {
                        "active": (item.get("active"), f"{prefix}.active"),
                        "amount": (_number(item.get("amount")), f"{prefix}.amount"),
                    }
                )
            elif event_type == "inspection":
                values.update(
                    {
                        "end_date": (_scalar(item.get(end_key)), f"{prefix}.{end_key}"),
                        "status": (item.get("inspectionStatus"), f"{prefix}.inspectionStatus"),
                        "title": (item.get("type"), f"{prefix}.type"),
                        "authority": (item.get("authorityName"), f"{prefix}.authorityName"),
                        "form": (item.get("form"), f"{prefix}.form"),
                    }
                )
            else:
                values.update(
                    {
                        "end_date": (_scalar(item.get(end_key)), f"{prefix}.{end_key}"),
                        "status": (item.get("status"), f"{prefix}.status"),
                        "title": (item.get("name"), f"{prefix}.name"),
                        "authority": (item.get("issuingAuthority"), f"{prefix}.issuingAuthority"),
                    }
                )
            result.item("legal_events", values)

    for index, value in enumerate(_array(report.get("procurements"))):
        item = _object(value)
        if item.get("procurementsYear") is None:
            continue
        prefix = f"report.procurements[{index}]"
        result.item(
            "procurements",
            {
                "item_index": (index, prefix),
                "year": (int(item["procurementsYear"]), f"{prefix}.procurementsYear"),
                "federal_law_code": (_text(item.get("federalLawCode")), f"{prefix}.federalLawCode"),
                "tender_admitted_count": (_number(item.get("tenderAdmittedCnt")), f"{prefix}.tenderAdmittedCnt"),
                "tender_winner_count": (_number(item.get("tenderWinnerCnt")), f"{prefix}.tenderWinnerCnt"),
                "contract_signed_count": (_number(item.get("contractSignedCnt")), f"{prefix}.contractSignedCnt"),
                "contract_signed_amount": (_number(item.get("contractSignedAmt")), f"{prefix}.contractSignedAmt"),
            },
        )
    return result


def _lookup(projection: Projection, field: str) -> tuple[Any, str] | None:
    if field.startswith("company_reports."):
        name = field.split(".", 1)[1]
        if name in projection.card["company_reports"]:
            return projection.card["company_reports"][name], projection.paths[field]
        return None
    match = _INDEXED_PATH.fullmatch(field)
    if not match:
        return None
    section = match.group("section")
    index = int(match.group("index"))
    name = match.group("field")
    values = projection.card.get(section)
    if not isinstance(values, list) or index >= len(values) or name not in values[index]:
        return None
    return values[index][name], projection.paths[field]


def _check(
    *,
    inn: str,
    tool: str,
    field: str,
    raw_path: str | None,
    expected: Any,
    actual: Any,
    status: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    return {
        "inn": inn,
        "tool": tool,
        "field": field,
        "raw_path": raw_path,
        "expected": expected,
        "actual": actual,
        "status": status or ("pass" if _equal(expected, actual) else "fail"),
        **({"reason": reason} if reason else {}),
    }


def validate_card_projection(
    inn: str, report: dict[str, Any], card: dict[str, Any]
) -> list[dict[str, Any]]:
    projection = project_raw_report(report)
    checks: list[dict[str, Any]] = []
    for field, raw_path in projection.paths.items():
        expected = _lookup(projection, field)
        if expected is None:
            continue
        match = _INDEXED_PATH.fullmatch(field)
        if match:
            values = card.get(match.group("section"), [])
            index = int(match.group("index"))
            actual = (
                values[index].get(match.group("field"))
                if isinstance(values, list) and index < len(values)
                else None
            )
        else:
            section, name = field.split(".", 1)
            actual = _object(card.get(section)).get(name)
        checks.append(
            _check(
                inn=inn,
                tool="read_model",
                field=field,
                raw_path=raw_path,
                expected=expected[0],
                actual=actual,
            )
        )
    return checks

