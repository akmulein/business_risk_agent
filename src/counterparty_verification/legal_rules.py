"""Deterministic checks for the legal-risk chapter.

Five checks, described in `tools_rules/analyze_legal.md` under the same names
that they report in `Observation.code`. A check never grades the counterparty: it
only states what deserves attention and points at the fields it read. No check
calls an LLM, the network or an external registry, so the same card always
produces the same result.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from functools import cached_property
from typing import Any

from .domain import (
    ArbitrationRecord,
    CompanyReport,
    CounterpartyCard,
    Evidence,
    FinancialReport,
    LegalEvent,
    Observation,
)
from .structure_rules import LICENSE_INACTIVE_MARKERS, as_date, as_float

# ---------------------------------------------------------------------------
# Thresholds: the single place to tune the checks with experts.
# ---------------------------------------------------------------------------

DEFENDANT_TO_PROCEEDS = 0.10
ENFORCEMENT_TO_PROCEEDS = 0.05
TREND_GROWTH = 2.0
TREND_YEARS = 3
LICENSE_EXPIRING_DAYS = 90
MAX_INSPECTION_DETAILS = 3
MAX_EVENT_IDS = 5

YEARLY_SOURCES = {"yearly", "by_year"}
STATUS_SOURCES = {"status", "by_status"}
INSPECTION_VIOLATION_MARKER = "наруш"
INSPECTION_CLEAN_MARKER = "без наруш"
INSPECTION_UPCOMING_MARKER = "предстоящ"


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _qty(value: float | int | None) -> str:
    if value is None:
        return "не указана"
    number = float(value)
    if abs(number - round(number)) < 1e-9:
        return f"{int(round(number)):,}".replace(",", " ")
    return f"{number:g}"


def _ratio_text(part: float, whole: float) -> str:
    return f"{part / whole * 100:.1f}%"


# ---------------------------------------------------------------------------
# Indexed access to the card
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class IndexedArbitration:
    """Arbitration row together with its position in `card.arbitration`."""

    index: int
    item: ArbitrationRecord

    def field(self, name: str) -> str:
        return f"arbitration[{self.index}].{name}"

    def evidence(self, name: str) -> Evidence:
        return Evidence(
            field=self.field(name),
            value=_json_value(getattr(self.item, name, None)),
        )


@dataclass(frozen=True, slots=True)
class IndexedEvent:
    """Legal-event row together with its position in `card.legal_events`."""

    index: int
    item: LegalEvent

    def field(self, name: str) -> str:
        return f"legal_events[{self.index}].{name}"

    def evidence(self, name: str) -> Evidence:
        return Evidence(
            field=self.field(name),
            value=_json_value(getattr(self.item, name, None)),
        )


@dataclass
class StatusBucket:
    """Count and amount for one role and case status, plus the source rows."""

    count: int = 0
    amount: float | None = None
    rows: list[IndexedArbitration] | None = None

    def __post_init__(self) -> None:
        if self.rows is None:
            self.rows = []

    @property
    def has_cases(self) -> bool:
        return self.count > 0 or (self.amount is not None and self.amount > 0)


@dataclass
class LegalView:
    """Read-only projection of the card, prepared once for all checks."""

    card: CounterpartyCard

    @cached_property
    def report(self) -> CompanyReport:
        return self.card.company_reports

    @cached_property
    def report_date(self) -> date:
        return as_date(self.report.report_date) or datetime.now(UTC).date()

    @cached_property
    def arbitration(self) -> list[IndexedArbitration]:
        return [
            IndexedArbitration(index=index, item=item)
            for index, item in enumerate(self.card.arbitration)
        ]

    @cached_property
    def events(self) -> list[IndexedEvent]:
        return [
            IndexedEvent(index=index, item=item)
            for index, item in enumerate(self.card.legal_events)
        ]

    @cached_property
    def status_rows(self) -> list[IndexedArbitration]:
        return [row for row in self.arbitration if row.item.source in STATUS_SOURCES]

    @cached_property
    def yearly_defendant(self) -> list[IndexedArbitration]:
        return [
            row
            for row in self.arbitration
            if row.item.source in YEARLY_SOURCES
            and row.item.role == "defendant"
            and row.item.year is not None
        ]

    @cached_property
    def common_arbitration(self) -> IndexedArbitration | None:
        return next(
            (
                row
                for row in self.status_rows
                if row.item.role == "all" and row.item.case_status == "all"
            ),
            None,
        )

    def status_bucket(self, role: str, case_status: str) -> StatusBucket:
        rows = [
            row
            for row in self.status_rows
            if row.item.role == role and row.item.case_status == case_status
        ]
        count = sum(row.item.case_count or 0 for row in rows)
        amounts = [as_float(row.item.amount) for row in rows if row.item.amount is not None]
        amount = sum(amounts) if amounts else None
        return StatusBucket(count=count, amount=amount, rows=rows)

    @cached_property
    def executions(self) -> list[IndexedEvent]:
        return [row for row in self.events if row.item.event_type == "execution"]

    @cached_property
    def active_executions(self) -> list[IndexedEvent]:
        return [row for row in self.executions if row.item.active is True]

    @cached_property
    def inspections(self) -> list[IndexedEvent]:
        return [row for row in self.events if row.item.event_type == "inspection"]

    @cached_property
    def licenses(self) -> list[IndexedEvent]:
        return [row for row in self.events if row.item.event_type == "license"]

    @cached_property
    def latest_finance_index(self) -> int | None:
        reports = self.card.financial_reports
        if not reports:
            return None
        return max(range(len(reports)), key=lambda index: reports[index].year)

    @cached_property
    def latest_finance(self) -> FinancialReport | None:
        if self.latest_finance_index is None:
            return None
        return self.card.financial_reports[self.latest_finance_index]

    @cached_property
    def proceeds(self) -> float | None:
        if self.latest_finance is None:
            return None
        return as_float(self.latest_finance.proceeds)

    @cached_property
    def profit(self) -> float | None:
        if self.latest_finance is None:
            return None
        return as_float(self.latest_finance.profit)

    @cached_property
    def total_assets(self) -> float | None:
        if self.latest_finance is None:
            return None
        return as_float(self.latest_finance.total_assets)

    def finance_evidence(self, name: str) -> Evidence | None:
        index = self.latest_finance_index
        if index is None:
            return None
        return Evidence(
            field=f"financial_reports[{index}].{name}",
            value=_json_value(getattr(self.latest_finance, name, None)),
        )


def build_view(card: CounterpartyCard) -> LegalView:
    return LegalView(card=card)


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LegalCheck:
    code: str
    title: str
    run: Callable[[LegalView], Observation | None]


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


def _report_evidence(view: LegalView, *names: str) -> list[Evidence]:
    return [
        Evidence(
            field=f"company_reports.{name}",
            value=_json_value(getattr(view.report, name, None)),
        )
        for name in names
    ]


def _bucket_evidence(bucket: StatusBucket, *names: str) -> list[Evidence]:
    return [row.evidence(name) for row in bucket.rows or [] for name in names]


def _passive_amount(pending: StatusBucket, appealed: StatusBucket) -> float | None:
    parts = [
        value
        for value in (pending.amount, appealed.amount)
        if value is not None
    ]
    if not parts:
        return None
    return sum(parts)


def _scale_clause(view: LegalView, amount: float | None, to_proceeds: float) -> str:
    """Extra sentence when the load is comparable to the company's scale."""
    if amount is None or amount <= 0:
        return ""
    profit = view.profit
    proceeds = view.proceeds
    if proceeds is not None and proceeds > 0 and amount / proceeds >= to_proceeds:
        return (
            f" Сумма сопоставима с масштабом: {_ratio_text(amount, proceeds)} "
            "последней выручки, поэтому её стоит соотнести с суммой сделки."
        )
    if profit is not None and profit > 0 and amount > profit:
        return (
            f" Сумма больше прибыли последнего года ({_qty(profit)}), "
            "что по практике проверки контрагентов повышает вероятность "
            "кассового разрыва."
        )
    if (
        (proceeds is None or proceeds <= 0)
        and view.total_assets is not None
        and view.total_assets > 0
        and amount / view.total_assets >= to_proceeds
    ):
        return (
            f" Выручка в отчёте не указана, а сумма составляет "
            f"{_ratio_text(amount, view.total_assets)} активов — "
            "соотнесите её с масштабом сделки."
        )
    return ""


def _finance_scale_evidence(view: LegalView) -> list[Evidence]:
    evidence: list[Evidence] = []
    for name in ("proceeds", "profit", "total_assets"):
        item = view.finance_evidence(name)
        if item is not None:
            evidence.append(item)
    return evidence


def _format_status_side(label: str, pending: StatusBucket, appealed: StatusBucket, finished: StatusBucket) -> str:
    return (
        f"{label}: открытых {pending.count} на сумму {_qty(pending.amount)}, "
        f"обжалованных {appealed.count} на сумму {_qty(appealed.amount)}, "
        f"закрытых {finished.count} на сумму {_qty(finished.amount)}"
    )


def _check_defendant_exposure(view: LegalView) -> Observation | None:
    """Текущая пассивная нагрузка: открытые и обжалованные дела ответчика."""
    pending = view.status_bucket("defendant", "pending")
    appealed = view.status_bucket("defendant", "appealed")
    finished = view.status_bucket("defendant", "finished")
    if not pending.has_cases and not appealed.has_cases:
        return None
    plaintiff_pending = view.status_bucket("plaintiff", "pending")
    plaintiff_appealed = view.status_bucket("plaintiff", "appealed")
    plaintiff_finished = view.status_bucket("plaintiff", "finished")
    load = _passive_amount(pending, appealed)
    scale = _scale_clause(view, load, DEFENDANT_TO_PROCEEDS)
    proceeds_text = ""
    if view.proceeds is not None and view.proceeds > 0 and load is not None:
        proceeds_text = (
            f" Пассивная нагрузка открытых и обжалованных дел — "
            f"{_ratio_text(load, view.proceeds)} выручки последнего года."
        )
    elif view.total_assets is not None and view.total_assets > 0 and load is not None:
        proceeds_text = (
            f" Выручка не указана; пассивная нагрузка — "
            f"{_ratio_text(load, view.total_assets)} активов."
        )
    evidence = [
        *_bucket_evidence(pending, "case_count", "amount", "case_status"),
        *_bucket_evidence(appealed, "case_count", "amount", "case_status"),
        *_bucket_evidence(finished, "case_count", "amount"),
        *_bucket_evidence(plaintiff_pending, "case_count", "amount"),
        *_report_evidence(view, "report_date"),
        *_finance_scale_evidence(view),
    ]
    return _observed(
        "defendant_exposure",
        "Текущая нагрузка как ответчик",
        f"{_format_status_side('Ответчик', pending, appealed, finished)}. "
        f"{_format_status_side('Истец', plaintiff_pending, plaintiff_appealed, plaintiff_finished)}. "
        "Закрытые дела сами по себе не говорят о текущем риске: смотреть стоит "
        f"на открытые и обжалованные.{proceeds_text}{scale}",
        evidence,
    )


def _yearly_totals(
    rows: list[IndexedArbitration],
) -> dict[int, tuple[int, float | None, list[IndexedArbitration]]]:
    grouped: dict[int, list[IndexedArbitration]] = defaultdict(list)
    for row in rows:
        year = row.item.year
        if year is None:
            continue
        grouped[year].append(row)
    totals: dict[int, tuple[int, float | None, list[IndexedArbitration]]] = {}
    for year, items in grouped.items():
        count = sum(item.item.case_count or 0 for item in items)
        amounts = [as_float(item.item.amount) for item in items if item.item.amount is not None]
        amount = sum(amounts) if amounts else None
        totals[year] = (count, amount, items)
    return totals


def _grew(current: float | None, previous: float | None) -> bool:
    if current is None or previous is None:
        return False
    if previous == 0:
        return current > 0
    return current >= TREND_GROWTH * previous


def _check_arbitration_trend(view: LegalView) -> Observation | None:
    """Рост дел ответчика за последние годы по годовой разбивке."""
    report_year = view.report_date.year
    window = {report_year - offset for offset in range(TREND_YEARS)}
    totals = {
        year: values
        for year, values in _yearly_totals(view.yearly_defendant).items()
        if year in window
    }
    years = sorted(totals)
    if len(years) < 2:
        return None
    last, previous = years[-1], years[-2]
    last_count, last_amount, last_rows = totals[last]
    prev_count, prev_amount, prev_rows = totals[previous]
    doubled = _grew(float(last_count), float(prev_count)) or _grew(last_amount, prev_amount)
    consecutive = False
    expected = [report_year - 2, report_year - 1, report_year]
    if all(year in totals for year in expected):
        counts = [totals[year][0] for year in expected]
        amounts = [totals[year][1] for year in expected]
        consecutive = counts[0] < counts[1] < counts[2]
        if not consecutive:
            first, second, third = amounts
            consecutive = (
                first is not None
                and second is not None
                and third is not None
                and first < second < third
            )
    if not doubled and not consecutive:
        return None
    series = ", ".join(
        f"{year}: {count} дел на сумму {_qty(amount)}"
        for year, (count, amount, _) in ((item, totals[item]) for item in years)
    )
    reason = (
        f"за {last} год показатель не меньше чем в {TREND_GROWTH:g} раза "
        f"выше {previous}"
        if doubled
        else f"три года подряд ({expected[0]}–{expected[2]}) нагрузка растёт"
    )
    trend_rows = (
        [row for year in expected for row in totals[year][2]]
        if consecutive
        else [*prev_rows, *last_rows]
    )
    evidence = [
        row.evidence(name)
        for row in trend_rows
        for name in ("year", "case_count", "amount")
    ]
    evidence.extend(_report_evidence(view, "report_date"))
    return _observed(
        "arbitration_trend",
        "Рост дел ответчика по годам",
        f"По годовым данным ответчика {series}. Это {reason}. "
        "Резкий рост исков к компании — ранний сигнал неплатежей; "
        "год без строки в отчёте не считается нулём дел.",
        evidence,
    )


def _check_enforcement_load(view: LegalView) -> Observation | None:
    """Активные исполнительные производства ФССП."""
    active = view.active_executions
    if not active:
        return None
    amounts = [as_float(row.item.amount) for row in active if row.item.amount is not None]
    total = sum(amounts) if amounts else None
    identifiers = [
        row.item.external_id for row in active if row.item.external_id
    ][:MAX_EVENT_IDS]
    dates = [
        as_date(row.item.event_date).isoformat()
        for row in active
        if as_date(row.item.event_date) is not None
    ][:MAX_EVENT_IDS]
    id_text = f" номера: {', '.join(identifiers)};" if identifiers else ""
    date_text = f" даты: {', '.join(dates)};" if dates else ""
    extra = ""
    if view.proceeds is not None and view.proceeds > 0 and total is not None:
        extra += f" Это {_ratio_text(total, view.proceeds)} выручки последнего года."
        if total / view.proceeds >= ENFORCEMENT_TO_PROCEEDS:
            extra += " Это уже не разовый штраф: сумма давит на исполнение сделки."
    elif (
        view.profit is not None
        and view.profit > 0
        and total is not None
        and total > view.profit
    ):
        extra += (
            f" Сумма больше прибыли последнего года ({_qty(view.profit)}), "
            "поэтому её стоит соотнести с исполнением сделки."
        )
    evidence = [
        *[row.evidence("active") for row in active],
        *[row.evidence("amount") for row in active],
        *[row.evidence("external_id") for row in active if row.item.external_id],
        *[row.evidence("event_date") for row in active if row.item.event_date],
        *_finance_scale_evidence(view),
    ]
    return _observed(
        "enforcement_load",
        "Активные исполнительные производства",
        f"Активных производств: {len(active)}, сумма: {_qty(total)}.{id_text}"
        f"{date_text} Неактивные записи не учитываются — это уже подтверждённый "
        f"и неисполненный долг.{extra}",
        evidence,
    )


def _inspection_is_notable(status: str | None) -> bool:
    text = (status or "").lower()
    if INSPECTION_UPCOMING_MARKER in text:
        return True
    if INSPECTION_CLEAN_MARKER in text:
        return False
    return INSPECTION_VIOLATION_MARKER in text


def _inspection_sort_key(entry: IndexedEvent) -> tuple[bool, date]:
    value = as_date(entry.item.event_date)
    return (value is not None, value or date.min)


def _format_inspection(entry: IndexedEvent) -> str:
    item = entry.item
    bits: list[str] = []
    if item.status:
        bits.append(item.status)
    if item.authority:
        bits.append(item.authority)
    if item.title:
        bits.append(item.title)
    if item.form:
        bits.append(f"форма: {item.form}")
    start = as_date(item.event_date)
    end = as_date(item.end_date)
    if start is not None:
        bits.append(f"с {start.isoformat()}")
    if end is not None:
        bits.append(f"по {end.isoformat()}")
    return ", ".join(bits) if bits else "сведения не указаны"


def _check_inspection_findings(view: LegalView) -> Observation | None:
    """Проверки с нарушениями или ещё не начавшиеся."""
    notable = [row for row in view.inspections if _inspection_is_notable(row.item.status)]
    if not notable:
        return None
    notable.sort(key=_inspection_sort_key, reverse=True)
    shown = notable[:MAX_INSPECTION_DETAILS]
    listed = "; ".join(_format_inspection(row) for row in shown)
    more = (
        f" Всего таких проверок: {len(notable)}."
        if len(notable) > len(shown)
        else ""
    )
    evidence = [
        evidence
        for row in shown
        for evidence in (
            row.evidence("status"),
            row.evidence("authority"),
            row.evidence("title"),
            row.evidence("form"),
            row.evidence("event_date"),
            row.evidence("end_date"),
        )
    ]
    return _observed(
        "inspection_findings",
        "Проверки с нарушениями или предстоящие",
        f"{listed}.{more} Завершённые без нарушений, отменённые и с неизвестным "
        "результатом сами по себе не поднимаются: смотреть стоит на нарушения "
        "и на то, что проверка ещё впереди.",
        evidence,
    )


def _license_inactive(status: str | None) -> bool:
    text = (status or "").upper()
    return any(marker in text for marker in LICENSE_INACTIVE_MARKERS)


def _check_license_validity(view: LegalView) -> Observation | None:
    """Лицензия есть в отчёте, но не действует или скоро кончится."""
    expired: list[IndexedEvent] = []
    expiring: list[IndexedEvent] = []
    for row in view.licenses:
        end = as_date(row.item.end_date)
        if _license_inactive(row.item.status):
            expired.append(row)
            continue
        if end is None:
            continue
        delta = (end - view.report_date).days
        if delta < 0:
            expired.append(row)
        elif delta <= LICENSE_EXPIRING_DAYS:
            expiring.append(row)
    if not expired and not expiring:
        return None
    parts: list[str] = []
    if expired:
        names = ", ".join(
            row.item.title or row.item.external_id or "без названия" for row in expired
        )
        parts.append(f"не действует: {names}")
    if expiring:
        names = ", ".join(
            f"{row.item.title or row.item.external_id or 'без названия'} "
            f"(до {as_date(row.item.end_date)})"
            for row in expiring
        )
        parts.append(
            f"истекает в ближайшие {LICENSE_EXPIRING_DAYS} дней: {names}"
        )
    evidence = _report_evidence(view, "report_date")
    for row in (*expired, *expiring):
        evidence.extend(
            [
                row.evidence("status"),
                row.evidence("end_date"),
                row.evidence("title"),
                row.evidence("external_id"),
                row.evidence("authority"),
                row.evidence("event_date"),
            ]
        )
    return _observed(
        "license_validity",
        "Лицензия не действует или скоро истекает",
        f"В отчёте указаны лицензии, у которых {'; '.join(parts)}. "
        "Действующие и бессрочные без близкой даты окончания не показываются. "
        "Соответствие лицензии основному ОКВЭД проверяет глава «Структура», "
        "здесь только срок уже попавших в отчёт разрешений.",
        evidence,
    )


CHECKS: tuple[LegalCheck, ...] = (
    LegalCheck(
        "defendant_exposure",
        "Текущая нагрузка как ответчик",
        _check_defendant_exposure,
    ),
    LegalCheck(
        "arbitration_trend",
        "Рост дел ответчика по годам",
        _check_arbitration_trend,
    ),
    LegalCheck(
        "enforcement_load",
        "Активные исполнительные производства",
        _check_enforcement_load,
    ),
    LegalCheck(
        "inspection_findings",
        "Проверки с нарушениями или предстоящие",
        _check_inspection_findings,
    ),
    LegalCheck(
        "license_validity",
        "Лицензия не действует или скоро истекает",
        _check_license_validity,
    ),
)


def run_checks(view: LegalView) -> list[Observation]:
    """Runs every check and returns the observations that fired."""
    observations: list[Observation] = []
    for check in CHECKS:
        observation = check.run(view)
        if observation is not None:
            observations.append(observation)
    return observations
