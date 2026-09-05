"""Deterministic checks for the general-information chapter.

Three checks, described in `tools_rules/analyze_general.md` under the same
names that they report in `Observation.code`. A check never grades the
counterparty: it only states what deserves attention and points at the fields
it read. No check calls an LLM, the network or an external registry, so the
same card always produces the same result.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from functools import cached_property
from typing import Any

from .domain import CompanyReport, CounterpartyCard, Evidence, Observation, RiskLevel

# ---------------------------------------------------------------------------
# Dictionaries: the single place to tune the checks with experts.
# ---------------------------------------------------------------------------

CLOSED_STATUSES = {"CLOSED", "закрытая"}
NOTABLE_ZSK_LEVELS = {"YELLOW", "RED"}
NOTABLE_PROVIDER_RISK_LEVELS = {RiskLevel.MEDIUM, RiskLevel.HIGH}


def _json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


@dataclass
class GeneralView:
    """Read-only projection of the card, prepared once for all checks."""

    card: CounterpartyCard

    @cached_property
    def report(self) -> CompanyReport:
        return self.card.company_reports

    def evidence(self, name: str) -> Evidence:
        return Evidence(
            field=f"company_reports.{name}",
            value=_json_value(getattr(self.report, name, None)),
        )


def build_view(card: CounterpartyCard) -> GeneralView:
    return GeneralView(card=card)


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GeneralCheck:
    code: str
    title: str
    run: Callable[[GeneralView], Observation | None]


def _observed(
    code: str,
    title: str,
    detail: str,
    evidence: Iterable[Evidence],
) -> Observation:
    return Observation(
        code=code,
        title=title,
        detail=detail,
        evidence=list(evidence),
    )


def _check_closed_status(view: GeneralView) -> Observation | None:
    """Статус организации в реестре."""
    report = view.report
    if report.status not in CLOSED_STATUSES:
        return None
    reason = f" Причина: {report.status_reason}." if report.status_reason else ""
    return _observed(
        "closed_status",
        "Организация помечена как закрытая",
        f"В отчёте указан статус «{report.status}».{reason} Стоит проверить "
        "актуальность выписки и решить, продолжать ли оформление сделки.",
        [view.evidence("status"), view.evidence("status_reason")],
    )


def _check_zsk_level(view: GeneralView) -> Observation | None:
    """Уровень «Знай своего клиента», присвоенный поставщиком данных."""
    level = view.report.zsk_risk_level
    if level not in NOTABLE_ZSK_LEVELS:
        return None
    return _observed(
        "zsk_level",
        "Поставщик данных отметил повышенный уровень ЗСК",
        f"Уровень «Знай своего клиента» в отчёте — {level}. Это оценка "
        "поставщика данных по его собственной методике, а не наш вывод — "
        "стоит посмотреть, чем она обоснована в первоисточнике.",
        [view.evidence("zsk_risk_level")],
    )


def _check_provider_risk_level(view: GeneralView) -> Observation | None:
    """Итоговый уровень риска, который поставщик данных указал в самом отчёте."""
    declared = view.report.risk_level
    if declared not in NOTABLE_PROVIDER_RISK_LEVELS:
        return None
    return _observed(
        "provider_risk_level",
        "В отчёте поставщика уже указан повышенный уровень риска",
        f"Поставщик данных присвоил отчёту уровень {declared.value}. Это его "
        "собственная оценка по своей методике — сверьте её с остальными "
        "главами анализа, прежде чем на неё полагаться.",
        [view.evidence("risk_level")],
    )


CHECKS: tuple[GeneralCheck, ...] = (
    GeneralCheck("closed_status", "Статус организации", _check_closed_status),
    GeneralCheck("zsk_level", "Уровень ЗСК", _check_zsk_level),
    GeneralCheck(
        "provider_risk_level",
        "Уровень риска поставщика данных",
        _check_provider_risk_level,
    ),
)


def run_checks(view: GeneralView) -> list[Observation]:
    """Runs every check and returns the observations that fired."""
    observations: list[Observation] = []
    for check in CHECKS:
        observation = check.run(view)
        if observation is not None:
            observations.append(observation)
    return observations
