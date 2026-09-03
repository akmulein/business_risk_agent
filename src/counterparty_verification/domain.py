from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    UNKNOWN = "UNKNOWN"


class CompanyReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    report_id: str
    report_date: date | str | None = None
    inn: str
    ogrn: str | None = None
    short_name: str | None = None
    full_name: str | None = None
    risk_level: RiskLevel | None = None
    zsk_risk_level: str | None = None
    kpp: str | None = None
    okpo: str | None = None
    address: str | None = None
    email: str | None = None
    website: str | None = None
    company_size: str | None = None
    staff: str | None = None
    registration_date: date | str | None = None
    years_from_registration: int | None = None
    status: str | None = None
    status_reason: str | None = None
    status_date: date | str | None = None
    share_capital: float | None = None
    branches_count: int | None = None
    raw_report_json: dict[str, Any] = Field(default_factory=dict)


class StructureItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    report_id: str
    company_inn: str
    subject_inn: str | None = None
    item_type: str
    item_index: int
    name: str | None = None
    related_inn: str | None = None
    related_ogrn: str | None = None
    role: str | None = None
    position: str | None = None
    code: str | None = None
    description: str | None = None
    share: float | None = None
    amount: float | None = None
    date_from: date | str | None = None
    active: bool | None = None
    registration_date: date | str | None = None
    address: str | None = None
    phone_type: str | None = None
    phone_code: str | None = None
    phone_number: str | None = None
    auth_person_name: str | None = None
    auth_person_position: str | None = None
    details_json: dict[str, Any] = Field(default_factory=dict)


class FinancialReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    report_id: str
    company_inn: str
    year: int
    proceeds: float | None = None
    profit: float | None = None
    total_assets: float | None = None
    current_assets_total: float | None = None
    stocks: float | None = None
    receivables: float | None = None
    bankroll: float | None = None
    uncurrent_assets_total: float | None = None
    fixed_assets: float | None = None
    total_liabilities: float | None = None
    capitals: float | None = None
    long_term_duties_total: float | None = None
    long_term_duties_others: float | None = None
    short_term_liabilities_total: float | None = None
    borrowed_funds: float | None = None
    accounts_payable: float | None = None
    sustainability: float | None = None
    solvency: float | None = None
    profitability: float | None = None


class SourceRiskFactor(BaseModel):
    model_config = ConfigDict(extra="allow")

    report_id: str
    company_inn: str
    sign: str
    item_index: int
    code: str | None = None
    name: str
    chapter: str | None = None


class ArbitrationRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    report_id: str
    company_inn: str
    source: str
    year: int | None = None
    role: str
    case_status: str
    case_count: int
    amount: float | None = None


class LegalEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    report_id: str
    company_inn: str
    event_type: str
    item_index: int
    external_id: str | None = None
    event_date: date | str | None = None
    end_date: date | str | None = None
    active: bool | None = None
    status: str | None = None
    amount: float | None = None
    title: str | None = None
    authority: str | None = None
    form: str | None = None
    details_json: dict[str, Any] = Field(default_factory=dict)


class ProcurementRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    report_id: str
    company_inn: str
    item_index: int
    year: int
    federal_law_code: str | None = None
    tender_admitted_count: int | None = None
    tender_winner_count: int | None = None
    contract_signed_count: int | None = None
    contract_signed_amount: float | None = None


class CounterpartyCard(BaseModel):
    """Aggregate assembled from the seven normalized database tables."""

    model_config = ConfigDict(extra="allow")

    company_reports: CompanyReport
    structure_items: list[StructureItem] = Field(default_factory=list)
    financial_reports: list[FinancialReport] = Field(default_factory=list)
    risk_factors: list[SourceRiskFactor] = Field(default_factory=list)
    arbitration: list[ArbitrationRecord] = Field(default_factory=list)
    legal_events: list[LegalEvent] = Field(default_factory=list)
    procurements: list[ProcurementRecord] = Field(default_factory=list)


class Evidence(BaseModel):
    field: str
    value: Any = None


class RiskFactor(BaseModel):
    title: str
    detail: str
    severity: RiskLevel
    evidence: list[Evidence] = Field(default_factory=list)


class ChapterResult(BaseModel):
    chapter: str
    risk_level: RiskLevel = RiskLevel.UNKNOWN
    conclusion: str
    factors: list[RiskFactor] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    data_sufficient: bool = True
    error: str | None = None


class AnalysisSummary(BaseModel):
    risk_level: RiskLevel
    summary: str
    key_factors: list[str] = Field(default_factory=list)


def validate_inn(value: str) -> str:
    if not value.isdigit() or len(value) != 10:
        raise ValueError("ИНН юридического лица должен содержать 10 цифр")
    digits = [int(char) for char in value]
    weights = (2, 4, 10, 3, 5, 9, 4, 6, 8)
    checksum = sum(digit * weight for digit, weight in zip(digits[:9], weights))
    if checksum % 11 % 10 != digits[9]:
        raise ValueError("Некорректная контрольная сумма ИНН")
    return value


class AnalysisRequest(BaseModel):
    inn: str

    @field_validator("inn")
    @classmethod
    def valid_inn(cls, value: str) -> str:
        return validate_inn(value.strip())


class AnalysisResponse(BaseModel):
    analysis_id: str
    inn: str
    summary: str
    risk_level: RiskLevel
    chapters: list[ChapterResult]


class QuestionRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)


class QuestionResponse(BaseModel):
    analysis_id: str
    answer: str
