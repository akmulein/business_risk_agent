"""Hermetic input cards and deterministic tool expectations.

Shared by tests/golden and eval/cases.py. No database or model calls occur
on import. required_signals/forbidden_signals check tool observations;
exact_numeric_values checks evidence, not LLM claims. The separate live
rubric is defined in eval/cases.py and reviewed against recorded inputs.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from counterparty_verification.domain import CounterpartyCard


@dataclass(frozen=True)
class GoldenCase:
    id: str
    description: str
    tags: tuple[str, ...]
    card: CounterpartyCard
    required_signals: tuple[tuple[str, str], ...] = ()
    forbidden_signals: tuple[tuple[str, str], ...] = ()
    expected_insufficient_chapters: tuple[str, ...] = ()
    exact_numeric_values: dict[str, float] = field(default_factory=dict)


def _card(**sections: object) -> CounterpartyCard:
    identity = {"report_id": "r-golden", "company_inn": sections["company_reports"]["inn"]}
    payload: dict[str, object] = {}
    for key, value in sections.items():
        if key == "company_reports":
            payload[key] = {"report_id": "r-golden", **value}
        elif isinstance(value, list):
            payload[key] = [{**identity, **item} for item in value]
        else:
            payload[key] = value
    return CounterpartyCard.model_validate(payload)


def _risk_factor(index: int, sign: str, code: str, name: str, chapter: str = "reestrs") -> dict:
    return {"sign": sign, "item_index": index, "code": code, "name": name, "chapter": chapter}


# ---------------------------------------------------------------------------
# 1. Bankruptcy
# ---------------------------------------------------------------------------

CASE_BANKRUPTCY = GoldenCase(
    id="bankruptcy",
    description="Company is in bankruptcy proceedings (конкурсное производство).",
    tags=("bankruptcy",),
    card=_card(
        company_reports={"inn": "7700000101", "short_name": "ООО БАНКРОТ", "status": "CURRENT", "risk_level": "HIGH"},
        risk_factors=[
            _risk_factor(0, "negative", "liquidationStatus", "Находится в реестре организаций проходящих процедуру банкротства.")
        ],
    ),
    required_signals=(("reputation", "chapter_reestrs"),),
)

# ---------------------------------------------------------------------------
# 2. Bankruptcy while the bank's own risk_level says LOW
# ---------------------------------------------------------------------------

CASE_BANKRUPTCY_LOW_RISK = GoldenCase(
    id="bankruptcy_low_risk",
    description="Bankruptcy proceedings despite the bank's own risk_level being LOW -- must not be parroted as 'low risk, safe'.",
    tags=("bankruptcy", "low_risk_trap"),
    card=_card(
        company_reports={"inn": "7700000102", "short_name": "ООО БАНКРОТ НИЗКИЙ РИСК", "status": "CURRENT", "risk_level": "LOW"},
        risk_factors=[
            _risk_factor(0, "negative", "liquidationStatus", "Находится в реестре организаций проходящих процедуру банкротства.")
        ],
    ),
    required_signals=(("reputation", "chapter_reestrs"),),
)

# ---------------------------------------------------------------------------
# 3. Execution proceedings
# ---------------------------------------------------------------------------

CASE_EXECUTION_PROCEEDINGS = GoldenCase(
    id="execution_proceedings",
    description="Active enforcement proceeding (execution).",
    tags=("execution_proceedings",),
    card=_card(
        company_reports={"inn": "7700000103", "short_name": "ООО ДОЛЖНИК", "status": "CURRENT"},
        legal_events=[
            {"event_type": "execution", "item_index": 0, "active": True, "amount": 650_000, "external_id": "111/24/00000-ИП"}
        ],
    ),
    required_signals=(("legal", "enforcement_load"),),
    exact_numeric_values={"сумма исполнительного производства": 650_000.0},
)

# ---------------------------------------------------------------------------
# 4. FNS blocking
# ---------------------------------------------------------------------------

CASE_FNS_BLOCKING = GoldenCase(
    id="fns_blocking",
    description="Active FNS (tax authority) account blocking.",
    tags=("fns_blocking",),
    card=_card(
        company_reports={"inn": "7700000104", "short_name": "ООО ЗАБЛОКИРОВАН", "status": "CURRENT"},
        risk_factors=[
            _risk_factor(0, "negative", "fnsBlocking", "Есть блокировки банковских счетов по постановлениям налоговой.")
        ],
    ),
    required_signals=(("reputation", "chapter_reestrs"),),
)

# ---------------------------------------------------------------------------
# 5. invalidAddress
# ---------------------------------------------------------------------------

CASE_INVALID_ADDRESS = GoldenCase(
    id="invalid_address",
    description="Company is registered with a fictitious (invalid) legal address.",
    tags=("invalid_address",),
    card=_card(
        company_reports={"inn": "7700000105", "short_name": "ООО ФИКТИВНЫЙ АДРЕС", "status": "CURRENT"},
        risk_factors=[
            _risk_factor(0, "negative", "invalidAddress", "Находится в реестре организаций с фиктивным адресом.")
        ],
    ),
    required_signals=(("reputation", "chapter_reestrs"),),
)

# ---------------------------------------------------------------------------
# 6. massAddress
# ---------------------------------------------------------------------------

CASE_MASS_ADDRESS = GoldenCase(
    id="mass_address",
    description="Company is registered at a mass-registration address.",
    tags=("mass_address",),
    card=_card(
        company_reports={"inn": "7700000106", "short_name": "ООО МАССОВЫЙ АДРЕС", "status": "CURRENT"},
        risk_factors=[
            _risk_factor(0, "negative", "massAddress", "Найден в реестре организаций с массовым адресом.")
        ],
    ),
    required_signals=(("reputation", "chapter_reestrs"),),
)

# ---------------------------------------------------------------------------
# 7. invalidAddress=true + massAddress=false -- the critical independence case
# ---------------------------------------------------------------------------

CASE_INVALID_ADDRESS_NOT_MASS = GoldenCase(
    id="invalid_address_not_mass",
    description=(
        "invalidAddress=true and massAddress=false are independent facts -- "
        "the model must not infer or claim massAddress=true just because "
        "invalidAddress=true is present."
    ),
    tags=("invalid_address", "mass_address", "independence"),
    card=_card(
        company_reports={"inn": "7700000107", "short_name": "ООО ФИКТИВНЫЙ НЕ МАССОВЫЙ", "status": "CURRENT"},
        risk_factors=[
            _risk_factor(0, "negative", "invalidAddress", "Находится в реестре организаций с фиктивным адресом."),
            _risk_factor(1, "positive", "massAddress", "Не найден в реестре организаций с массовым адресом."),
        ],
    ),
    required_signals=(("reputation", "chapter_reestrs"),),
)

# ---------------------------------------------------------------------------
# 8. invalidRegistrationData
# ---------------------------------------------------------------------------

CASE_INVALID_REGISTRATION_DATA = GoldenCase(
    id="invalid_registration_data",
    description="Company is registered with unreliable registration data.",
    tags=("invalid_registration_data",),
    card=_card(
        company_reports={"inn": "7700000108", "short_name": "ООО НЕДОСТОВЕРНЫЕ ДАННЫЕ", "status": "CURRENT"},
        risk_factors=[
            _risk_factor(
                0, "negative", "invalidRegistrationData",
                "Находится в реестре организаций с недостоверными регистрационными данными.",
            )
        ],
    ),
    required_signals=(
        ("reputation", "chapter_reestrs"),
        ("structure", "provider_flags"),
    ),
)

# ---------------------------------------------------------------------------
# 9. Arbitration -- plaintiff only
# ---------------------------------------------------------------------------

CASE_ARBITRATION_PLAINTIFF = GoldenCase(
    id="arbitration_plaintiff",
    description=(
        "Company sues others (plaintiff) -- must not be read as being sued. "
        "NOTE: legal.py's defendant_exposure only reports a plaintiff row as "
        "*context text alongside* a defendant row (see test_legal_rules.py's "
        "test_pending_defendant_is_observed_without_yearly_double_count); a "
        "plaintiff-only card with no defendant row triggers no check at all "
        "in legal.py, so this scenario has no exact_numeric_values -- the "
        "tool layer genuinely does not surface a standalone plaintiff count "
        "today. Only the absence of a false defendant claim is evaluated."
    ),
    tags=("arbitration", "plaintiff"),
    card=_card(
        company_reports={"inn": "7700000109", "short_name": "ООО ИСТЕЦ", "status": "CURRENT"},
        arbitration=[
            {"id": "arb-0", "source": "status", "role": "plaintiff", "case_status": "pending", "case_count": 150, "amount": 5_000_000}
        ],
    ),
    forbidden_signals=(("legal", "defendant_exposure"),),
)

# ---------------------------------------------------------------------------
# 10. Arbitration -- defendant
# ---------------------------------------------------------------------------

CASE_ARBITRATION_DEFENDANT = GoldenCase(
    id="arbitration_defendant",
    description="Company is sued (defendant) with an open case.",
    tags=("arbitration", "defendant"),
    card=_card(
        company_reports={"inn": "7700000110", "short_name": "ООО ОТВЕТЧИК", "status": "CURRENT"},
        arbitration=[
            {"id": "arb-0", "source": "status", "role": "defendant", "case_status": "pending", "case_count": 5, "amount": 3_000_000}
        ],
        financial_reports=[{"year": 2025, "proceeds": 10_000_000, "profit": 200_000}],
    ),
    required_signals=(("legal", "defendant_exposure"),),
    exact_numeric_values={"сумма иска ответчиком": 3_000_000.0, "количество дел ответчиком": 5.0},
)

# ---------------------------------------------------------------------------
# 11. Missing data everywhere
# ---------------------------------------------------------------------------

CASE_MISSING_DATA = GoldenCase(
    id="missing_data",
    description=(
        "No risk_factors/arbitration/legal_events/financial_reports/"
        "procurements/structure_items at all -- absence of data must read "
        "as 'insufficient data', never as a confirmed absence of risk."
    ),
    tags=("missing_data",),
    card=_card(company_reports={"inn": "7700000111", "short_name": "ООО ПУСТОЙ ОТЧЁТ", "status": "CURRENT"}),
    expected_insufficient_chapters=("structure", "legal", "reputation", "finance", "procurement"),
)

# ---------------------------------------------------------------------------
# 12. Multiple negative factors at once
# ---------------------------------------------------------------------------

CASE_MULTIPLE_NEGATIVE_FACTORS = GoldenCase(
    id="multiple_negative_factors",
    description="Several independent negative factors present simultaneously -- none should be dropped.",
    tags=("multiple_factors",),
    card=_card(
        company_reports={"inn": "7700000112", "short_name": "ООО МНОГО РИСКОВ", "status": "CURRENT", "risk_level": "HIGH"},
        risk_factors=[
            _risk_factor(0, "negative", "fnsBlocking", "Есть блокировки банковских счетов по постановлениям налоговой."),
            _risk_factor(1, "negative", "invalidAddress", "Находится в реестре организаций с фиктивным адресом."),
            _risk_factor(2, "negative", "liquidationStatus", "Находится в реестре организаций проходящих процедуру банкротства."),
        ],
        legal_events=[{"event_type": "execution", "item_index": 0, "active": True, "amount": 400_000, "external_id": "1"}],
    ),
    required_signals=(("reputation", "chapter_reestrs"), ("legal", "enforcement_load")),
)

# ---------------------------------------------------------------------------
# 13. ООО МАКСМАРКЕТ -- mandatory regression case (real seed data, ИНН 5032257375)
# ---------------------------------------------------------------------------

CASE_MAKSMARKET = GoldenCase(
    id="maksmarket",
    description=(
        "Partial fixture based on data/seed/contractors_audit.snapshot.json "
        "(ИНН 5032257375): bankrupt with конкурсное производство, active "
        "execution proceedings, FNS blocking, invalidAddress=true, "
        "invalidRegistrationData=true, massAddress=false, and a 2024 "
        "arbitration defendant row (case_count=258, amount=2 589 790 444) "
        "-- while the bank's own risk_level says LOW."
    ),
    tags=("bankruptcy", "low_risk_trap", "execution_proceedings", "fns_blocking",
          "invalid_address", "invalid_registration_data", "mass_address",
          "independence", "arbitration", "defendant", "large_amounts",
          "multiple_factors", "regression"),
    card=_card(
        company_reports={
            "inn": "5032257375",
            "ogrn": "1165032060050",
            "short_name": 'ООО "МАКСМАРКЕТ"',
            "full_name": 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "МАКСМАРКЕТ"',
            "status": "CURRENT",
            "status_reason": "Юридическое лицо признано несостоятельным (банкротом) и в отношении него открыто конкурсное производство",
            "risk_level": "LOW",
            "zsk_risk_level": "GREEN",
        },
        risk_factors=[
            _risk_factor(0, "negative", "executionProceedings",
                         "Есть действующие исполнительные производства, в которых выступает в качестве ответчика.",
                         chapter="execproc"),
            _risk_factor(1, "negative", "liquidationStatus",
                         "Находится в реестре организаций проходящих процедуру банкротства.",
                         chapter="reestrs"),
            _risk_factor(2, "negative", "invalidAddress",
                         "Находится в реестре организаций с фиктивным адресом.",
                         chapter="reestrs"),
            _risk_factor(3, "negative", "arbitrationDefendant",
                         "Есть арбитражные дела, в которых выступает в качестве ответчика.",
                         chapter="arbitr"),
            _risk_factor(4, "negative", "invalidRegistrationData",
                         "Находится в реестре организаций с недостоверными регистрационными данными.",
                         chapter="reestrs"),
            _risk_factor(5, "negative", "fnsBlocking",
                         "Есть блокировки банковских счетов по постановлениям налоговой.",
                         chapter="reestrs"),
            _risk_factor(6, "positive", "massAddress",
                         "Не найден в реестре организаций с массовым адресом.",
                         chapter="reestrs"),
        ],
        arbitration=[
            {
                "id": "arb-2024",
                "case_status": "all",
                "source": "yearly",
                "year": 2024,
                "role": "defendant",
                "case_count": 258,
                "amount": 2_589_790_444,
            },
        ],
        legal_events=[
            {"event_type": "execution", "item_index": 0, "active": True, "external_id": "2014965/23/50061-ИП"},
        ],
    ),
    required_signals=(
        ("reputation", "chapter_reestrs"),
        ("reputation", "chapter_execproc"),
        ("reputation", "chapter_arbitr"),
        ("legal", "enforcement_load"),
        ("structure", "provider_flags"),
    ),
    # Annual totals are not current pending exposure and do not reach summary context.
    exact_numeric_values={},
)

ALL_CASES: tuple[GoldenCase, ...] = (
    CASE_BANKRUPTCY,
    CASE_BANKRUPTCY_LOW_RISK,
    CASE_EXECUTION_PROCEEDINGS,
    CASE_FNS_BLOCKING,
    CASE_INVALID_ADDRESS,
    CASE_MASS_ADDRESS,
    CASE_INVALID_ADDRESS_NOT_MASS,
    CASE_INVALID_REGISTRATION_DATA,
    CASE_ARBITRATION_PLAINTIFF,
    CASE_ARBITRATION_DEFENDANT,
    CASE_MISSING_DATA,
    CASE_MULTIPLE_NEGATIVE_FACTORS,
    CASE_MAKSMARKET,
)

CASES_BY_ID: dict[str, GoldenCase] = {case.id: case for case in ALL_CASES}
