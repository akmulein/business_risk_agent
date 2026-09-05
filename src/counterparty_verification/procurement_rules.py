"""Deterministic checks for the public-procurement chapter.

Five checks, described in `tools_rules/analyze_procurement.md` under the same
names that they report in `Observation.code`. A check never grades the
counterparty: it only states what deserves attention and points at the
fields it read. No check calls an LLM, the network or an external registry
(the ЕИС or the Реестр недобросовестных поставщиков are not in the card), so
the same card always produces the same result.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from functools import cached_property
from typing import Any

from .domain import CompanyReport, CounterpartyCard, Evidence, Observation, ProcurementRecord
from .structure_rules import as_date

# ---------------------------------------------------------------------------
# Thresholds: the single place to tune the checks with experts.
# ---------------------------------------------------------------------------

MIN_ADMITTED_FOR_WIN_RATE = 5
LOW_WIN_RATE = 0.15
HIGH_WIN_RATE = 0.90
DROPOFF_YEARS_GAP = 2
CONTRACT_SPIKE_MULTIPLIER = 4.0
MIN_SIGNED_FOR_LAW_MIX = 3
LAW_223_SHARE_HIGH = 0.8


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


def _is_223_fz(code: str | None) -> bool:
    return bool(code) and "223" in code


# ---------------------------------------------------------------------------
# Indexed access to the card
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class IndexedProcurement:
    """Procurement row together with its position in `card.procurements`.

    The position builds evidence paths such as `procurements[0].year`, which
    are validated against the card by `agents.flatten_field_paths`.
    """

    index: int
    item: ProcurementRecord

    def field(self, name: str) -> str:
        return f"procurements[{self.index}].{name}"

    def evidence(self, name: str) -> Evidence:
        return Evidence(
            field=self.field(name),
            value=_json_value(getattr(self.item, name, None)),
        )


@dataclass(frozen=True, slots=True)
class YearAggregate:
    """Sum of every row reported for one `procurementsYear`.

    A year can carry more than one row (e.g. a 44-ФЗ row and a 223-ФЗ row),
    so the counts that describe "the year" are sums across its rows, not a
    single row's fields.
    """

    year: int
    records: tuple[IndexedProcurement, ...]

    @property
    def admitted(self) -> int:
        return sum(int(r.item.tender_admitted_count or 0) for r in self.records)

    @property
    def winners(self) -> int:
        return sum(int(r.item.tender_winner_count or 0) for r in self.records)

    @property
    def signed_count(self) -> int:
        return sum(int(r.item.contract_signed_count or 0) for r in self.records)

    @property
    def signed_amount(self) -> float:
        return sum(float(r.item.contract_signed_amount or 0) for r in self.records)

    def evidence(self, *names: str) -> list[Evidence]:
        return [
            record.evidence(name)
            for record in self.records
            for name in names
            if getattr(record.item, name, None) is not None
        ]


@dataclass
class ProcurementView:
    """Read-only projection of `card.procurements`, prepared once."""

    card: CounterpartyCard

    @cached_property
    def indexed(self) -> list[IndexedProcurement]:
        return [
            IndexedProcurement(index=index, item=item)
            for index, item in enumerate(self.card.procurements)
        ]

    @cached_property
    def by_year(self) -> dict[int, YearAggregate]:
        grouped: dict[int, list[IndexedProcurement]] = defaultdict(list)
        for entry in self.indexed:
            grouped[entry.item.year].append(entry)
        return {
            year: YearAggregate(year=year, records=tuple(entries))
            for year, entries in grouped.items()
        }

    @cached_property
    def years(self) -> list[int]:
        """Distinct years present in the card, oldest first."""
        return sorted(self.by_year)

    @cached_property
    def latest_year(self) -> YearAggregate | None:
        return self.by_year[self.years[-1]] if self.years else None

    @property
    def report(self) -> CompanyReport:
        return self.card.company_reports

    @cached_property
    def report_date(self) -> date:
        return as_date(self.report.report_date) or datetime.now(UTC).date()


def build_view(card: CounterpartyCard) -> ProcurementView:
    return ProcurementView(card=card)


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ProcurementCheck:
    code: str
    title: str
    run: Callable[[ProcurementView], Observation | None]


def _observed(code: str, title: str, detail: str, evidence: list[Evidence]) -> Observation:
    return Observation(code=code, title=title, detail=detail, evidence=evidence)


def _check_abnormal_win_rate(view: ProcurementView) -> Observation | None:
    """Доля выигранных тендеров от поданных заявок за всю историю."""
    admitted = sum(agg.admitted for agg in view.by_year.values())
    if admitted < MIN_ADMITTED_FOR_WIN_RATE:
        return None
    winners = sum(agg.winners for agg in view.by_year.values())
    win_rate = winners / admitted
    evidence = [
        e
        for agg in view.by_year.values()
        for e in agg.evidence("tender_admitted_count", "tender_winner_count", "year")
    ]
    if win_rate <= LOW_WIN_RATE:
        return _observed(
            "abnormal_win_rate",
            "Низкая результативность участия в тендерах",
            f"Из {admitted} поданных заявок выиграно {winners} "
            f"({win_rate * 100:.1f}%, не больше {LOW_WIN_RATE * 100:g}%). "
            "Стоит уточнить, почему компания системно не побеждает — это "
            "может говорить о слабой конкурентоспособности либо об участии "
            "для видимости.",
            evidence,
        )
    if win_rate >= HIGH_WIN_RATE:
        return _observed(
            "abnormal_win_rate",
            "Почти стопроцентная результативность участия в тендерах",
            f"Из {admitted} поданных заявок выиграно {winners} "
            f"({win_rate * 100:.1f}%, не меньше {HIGH_WIN_RATE * 100:g}%). "
            "Само по себе это не нарушение, но при таком количестве тендеров "
            "заслуживает отдельной проверки на признаки согласованности с "
            "заказчиком.",
            evidence,
        )
    return None


def _check_contract_signing_gap(view: ProcurementView) -> Observation | None:
    """Победы в тендерах, не завершившиеся подписанием контракта."""
    gaps = sorted(
        (agg.year, agg.winners - agg.signed_count)
        for agg in view.by_year.values()
        if agg.winners > agg.signed_count
    )
    if not gaps:
        return None
    total_gap = sum(gap for _, gap in gaps)
    years_text = "; ".join(f"{year} год — {gap}" for year, gap in gaps)
    evidence = [
        e
        for year, _ in gaps
        for e in view.by_year[year].evidence(
            "tender_winner_count", "contract_signed_count", "year"
        )
    ]
    return _observed(
        "contract_signing_gap",
        "Победа в тендере не завершилась подписанием контракта",
        f"Контрактов подписано меньше, чем было побед: {years_text} "
        f"(всего недостаёт {total_gap}). По 44-ФЗ уклонение от заключения "
        "контракта после победы — самостоятельное основание для включения в "
        "реестр недобросовестных поставщиков; стоит уточнить причину "
        "расхождения у контрагента.",
        evidence,
    )


def _check_activity_dropoff(view: ProcurementView) -> Observation | None:
    """Отсутствие участия в закупках в последние годы при наличии истории.

    Строка в `procurements[]` появляется за год, в котором компания реально
    что-то делала на этой площадке, поэтому отсутствие записей за
    последние годы — само по себе сигнал, а не то, что нужно отдельно
    проверять по счётчикам последнего года.
    """
    years = view.years
    if not years:
        return None
    had_history = any(
        view.by_year[year].winners > 0 or view.by_year[year].signed_count > 0
        for year in years
    )
    if not had_history:
        return None
    gap_years = view.report_date.year - years[-1]
    if gap_years < DROPOFF_YEARS_GAP:
        return None
    evidence = [
        e
        for year in years
        for e in view.by_year[year].evidence(
            "tender_admitted_count",
            "tender_winner_count",
            "contract_signed_count",
            "year",
        )
    ] + [
        Evidence(
            field="company_reports.report_date",
            value=_json_value(view.report.report_date),
        )
    ]
    return _observed(
        "activity_dropoff",
        "Участие в закупках прекратилось несмотря на прошлую активность",
        f"Компания участвовала в закупках в {len(years)} год(лет), последний "
        f"раз — в {years[-1]} году, а по состоянию на "
        f"{view.report_date.year} год это {gap_years} год(лет) подряд без "
        "единой заявки. Стоит уточнить причину: истечение аккредитации, "
        "попадание в реестр недобросовестных поставщиков или смена профиля "
        "деятельности.",
        evidence,
    )


def _check_contract_size_spike(view: ProcurementView) -> Observation | None:
    """Резкий рост среднего размера контракта относительно прошлых лет."""
    years_with_contracts = [
        view.by_year[year] for year in view.years if view.by_year[year].signed_count > 0
    ]
    if len(years_with_contracts) < 2:
        return None
    *previous, latest = years_with_contracts
    latest_avg = latest.signed_amount / latest.signed_count
    previous_avgs = [agg.signed_amount / agg.signed_count for agg in previous]
    baseline_avg = sum(previous_avgs) / len(previous_avgs)
    if baseline_avg <= 0 or latest_avg < baseline_avg * CONTRACT_SPIKE_MULTIPLIER:
        return None
    evidence = [
        e
        for agg in years_with_contracts
        for e in agg.evidence("contract_signed_amount", "contract_signed_count", "year")
    ]
    return _observed(
        "contract_size_spike",
        "Резкий рост среднего размера контракта",
        f"Средний контракт {latest.year} года — {_qty(latest_avg)} ₽, это в "
        f"{latest_avg / baseline_avg:.1f} раза больше среднего по прошлым "
        f"годам ({_qty(baseline_avg)} ₽). Стоит уточнить, чем обоснован "
        "масштаб нового контракта и не превышает ли он обычные для компании "
        "обороты.",
        evidence,
    )


def _check_law_regime_mix(view: ProcurementView) -> Observation | None:
    """Доля контрактов, заключённых по 223-ФЗ, а не по 44-ФЗ."""
    total_amount = sum(agg.signed_amount for agg in view.by_year.values())
    total_count = sum(agg.signed_count for agg in view.by_year.values())
    if total_count < MIN_SIGNED_FOR_LAW_MIX:
        return None
    if total_amount > 0:
        matched = sum(
            float(r.item.contract_signed_amount or 0)
            for r in view.indexed
            if _is_223_fz(r.item.federal_law_code)
        )
        share = matched / total_amount
        basis = "по сумме контрактов"
    else:
        matched = sum(
            int(r.item.contract_signed_count or 0)
            for r in view.indexed
            if _is_223_fz(r.item.federal_law_code)
        )
        share = matched / total_count
        basis = "по количеству контрактов"
    if share < LAW_223_SHARE_HIGH:
        return None
    evidence = [
        r.evidence(name)
        for r in view.indexed
        for name in (
            "federal_law_code",
            "contract_signed_amount",
            "contract_signed_count",
            "year",
        )
        if getattr(r.item, name, None) is not None
    ]
    return _observed(
        "law_regime_mix",
        "Закупки почти полностью проходят по 223-ФЗ",
        f"Доля контрактов по 223-ФЗ составляет {share * 100:.1f}% ({basis}, "
        f"не меньше {LAW_223_SHARE_HIGH * 100:g}%). Закон 223-ФЗ даёт "
        "заказчику больше свободы в процедурах закупки, чем 44-ФЗ, — это не "
        "нарушение само по себе, но стоит отдельно посмотреть на условия "
        "таких контрактов.",
        evidence,
    )


CHECKS: tuple[ProcurementCheck, ...] = (
    ProcurementCheck(
        "abnormal_win_rate",
        "Результативность участия в тендерах",
        _check_abnormal_win_rate,
    ),
    ProcurementCheck(
        "contract_signing_gap",
        "Победы без подписанного контракта",
        _check_contract_signing_gap,
    ),
    ProcurementCheck(
        "activity_dropoff",
        "Прекращение участия в закупках",
        _check_activity_dropoff,
    ),
    ProcurementCheck(
        "contract_size_spike",
        "Скачок размера контракта",
        _check_contract_size_spike,
    ),
    ProcurementCheck(
        "law_regime_mix",
        "Структура закупок по 44-ФЗ/223-ФЗ",
        _check_law_regime_mix,
    ),
)


def run_checks(view: ProcurementView) -> list[Observation]:
    """Runs every check and returns the observations that fired."""
    observations: list[Observation] = []
    for check in CHECKS:
        observation = check.run(view)
        if observation is not None:
            observations.append(observation)
    return observations
