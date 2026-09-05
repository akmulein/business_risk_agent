"""Deterministic checks for the financial-indicators chapter.

Five checks, described in `tools_rules/analyze_finance.md` under the same names
that they report in `Observation.code`. A check never grades the counterparty: it
only states what deserves attention and points at the fields it read. No check
calls an LLM, the network or an external registry, so the same card always
produces the same result.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from functools import cached_property
from typing import Any

from .domain import CounterpartyCard, Evidence, FinancialReport, Observation
from .structure_rules import as_float

# ---------------------------------------------------------------------------
# Thresholds: the single place to tune the checks with experts.
# ---------------------------------------------------------------------------

LIQUIDITY_THRESHOLD = 1.0
SUSTAINABILITY_LOW = 0.5
LEVERAGE_HIGH = 0.85


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


# ---------------------------------------------------------------------------
# Indexed access to the card
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class IndexedFinance:
    """Financial-report row together with its position in `card.financial_reports`.

    The position builds evidence paths such as `financial_reports[1].capitals`,
    which are validated against the card by `agents.flatten_field_paths`.
    """

    index: int
    item: FinancialReport

    def field(self, name: str) -> str:
        return f"financial_reports[{self.index}].{name}"

    def evidence(self, name: str) -> Evidence:
        return Evidence(
            field=self.field(name),
            value=_json_value(getattr(self.item, name, None)),
        )


@dataclass
class FinanceView:
    """Read-only projection of the card, prepared once for all checks."""

    card: CounterpartyCard

    @cached_property
    def reports(self) -> list[IndexedFinance]:
        """All reports, oldest first, keeping their original card index."""
        indexed = [
            IndexedFinance(index=index, item=item)
            for index, item in enumerate(self.card.financial_reports)
        ]
        return sorted(indexed, key=lambda entry: entry.item.year)

    @cached_property
    def latest(self) -> IndexedFinance | None:
        return self.reports[-1] if self.reports else None

    @cached_property
    def previous(self) -> IndexedFinance | None:
        return self.reports[-2] if len(self.reports) > 1 else None

    @cached_property
    def earliest_of_three(self) -> IndexedFinance | None:
        return self.reports[-3] if len(self.reports) > 2 else None


def build_view(card: CounterpartyCard) -> FinanceView:
    return FinanceView(card=card)


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FinanceCheck:
    code: str
    title: str
    run: Callable[[FinanceView], Observation | None]


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


def _check_net_loss(view: FinanceView) -> Observation | None:
    """Финансовый результат последнего отчётного года."""
    latest = view.latest
    if latest is None:
        return None
    profit = as_float(latest.item.profit)
    if profit is None or profit >= 0:
        return None
    return _observed(
        "net_loss",
        "Последний отчётный год закрыт с убытком",
        f"По итогам {latest.item.year} года финансовый результат — убыток "
        f"{_qty(abs(profit))} ₽. Стоит уточнить причину и сравнить с "
        "показателями предыдущих периодов, прежде чем делать вывод.",
        [latest.evidence("profit"), latest.evidence("year")],
    )


def _check_revenue_decline(view: FinanceView) -> Observation | None:
    """Динамика выручки между последними отчётными годами."""
    latest, previous = view.latest, view.previous
    if latest is None or previous is None:
        return None
    current = as_float(latest.item.proceeds)
    prior = as_float(previous.item.proceeds)
    if current is None or prior is None or prior <= 0 or current >= prior:
        return None
    change = (current - prior) / prior * 100
    evidence = [
        latest.evidence("proceeds"),
        latest.evidence("year"),
        previous.evidence("proceeds"),
        previous.evidence("year"),
    ]
    two_years_running = ""
    earliest = view.earliest_of_three
    if earliest is not None:
        before_prior = as_float(earliest.item.proceeds)
        if before_prior is not None and before_prior > 0 and prior < before_prior:
            two_years_running = (
                f" Снижение отмечается второй год подряд: {earliest.item.year} → "
                f"{previous.item.year} → {latest.item.year}."
            )
            evidence += [earliest.evidence("proceeds"), earliest.evidence("year")]
    return _observed(
        "revenue_decline",
        "Выручка снизилась к предыдущему отчётному году",
        f"Выручка изменилась с {_qty(prior)} ₽ ({previous.item.year} год) до "
        f"{_qty(current)} ₽ ({latest.item.year} год), это {change:.1f}%."
        f"{two_years_running} Стоит уточнить причину падения у контрагента.",
        evidence,
    )


def _check_liquidity_gap(view: FinanceView) -> Observation | None:
    """Оборотные активы против краткосрочных обязательств последнего года."""
    latest = view.latest
    if latest is None:
        return None
    solvency = as_float(latest.item.solvency)
    current_assets = as_float(latest.item.current_assets_total)
    short_term = as_float(latest.item.short_term_liabilities_total)
    computed_ratio = (
        current_assets / short_term
        if current_assets is not None and short_term is not None and short_term > 0
        else None
    )
    value = solvency if solvency is not None else computed_ratio
    if value is None or value >= LIQUIDITY_THRESHOLD:
        return None
    evidence = [latest.evidence("year")]
    if solvency is not None:
        evidence.append(latest.evidence("solvency"))
        source_text = "Коэффициент платёжеспособности из отчёта"
    else:
        source_text = "Отношение оборотных активов к краткосрочным обязательствам"
    cross_check = ""
    if current_assets is not None and short_term is not None:
        evidence += [
            latest.evidence("current_assets_total"),
            latest.evidence("short_term_liabilities_total"),
        ]
        if solvency is not None and computed_ratio is not None:
            cross_check = (
                f" Отдельно рассчитанное отношение оборотных активов к "
                f"краткосрочным обязательствам по балансу — {computed_ratio:.2f}."
            )
    return _observed(
        "liquidity_gap",
        "Оборотные активы не покрывают краткосрочные обязательства",
        f"{source_text} за {latest.item.year} год — {value:.2f} (меньше "
        f"{LIQUIDITY_THRESHOLD:g}).{cross_check} Стоит уточнить структуру "
        "оборотных активов и график погашения краткосрочных обязательств.",
        evidence,
    )


def _check_negative_equity(view: FinanceView) -> Observation | None:
    """Капитал и резервы последнего отчётного года."""
    latest = view.latest
    if latest is None:
        return None
    capitals = as_float(latest.item.capitals)
    if capitals is None or capitals >= 0:
        return None
    total_liabilities = as_float(latest.item.total_liabilities)
    total_assets = as_float(latest.item.total_assets)
    scale = ""
    evidence = [
        latest.evidence("capitals"),
        latest.evidence("year"),
    ]
    if total_liabilities is not None and total_assets is not None:
        scale = (
            f" Всего пассивов — {_qty(total_liabilities)} ₽, "
            f"всего активов — {_qty(total_assets)} ₽."
        )
        evidence += [
            latest.evidence("total_liabilities"),
            latest.evidence("total_assets"),
        ]
    return _observed(
        "negative_equity",
        "Капитал и резервы отрицательны",
        f"По итогам {latest.item.year} года капитал и резервы — "
        f"{_qty(capitals)} ₽, то есть обязательства превышают активы.{scale} "
        "Обычно такое значение означает накопленный непокрытый убыток — стоит "
        "уточнить его происхождение отдельно.",
        evidence,
    )


def _check_leverage(view: FinanceView) -> Observation | None:
    """Доля собственного капитала и долгосрочных пассивов в активах."""
    latest = view.latest
    if latest is None:
        return None
    sustainability = as_float(latest.item.sustainability)
    total_liabilities = as_float(latest.item.total_liabilities)
    total_assets = as_float(latest.item.total_assets)
    computed_debt_share = (
        total_liabilities / total_assets
        if total_liabilities is not None
        and total_assets is not None
        and total_assets > 0
        else None
    )
    if sustainability is not None:
        if sustainability >= SUSTAINABILITY_LOW:
            return None
        evidence = [latest.evidence("sustainability"), latest.evidence("year")]
        detail = (
            f"Коэффициент финансовой устойчивости за {latest.item.year} год — "
            f"{sustainability:.2f} (меньше {SUSTAINABILITY_LOW:g}): собственный "
            "капитал и долгосрочные обязательства покрывают меньше половины "
            "активов."
        )
    elif computed_debt_share is not None:
        if computed_debt_share < LEVERAGE_HIGH:
            return None
        evidence = [
            latest.evidence("total_liabilities"),
            latest.evidence("total_assets"),
            latest.evidence("year"),
        ]
        detail = (
            f"Коэффициент устойчивости в отчёте не указан. По балансу доля "
            f"обязательств в активах за {latest.item.year} год — "
            f"{computed_debt_share * 100:.1f}% (не меньше "
            f"{LEVERAGE_HIGH * 100:g}%)."
        )
    else:
        return None
    detail += (
        " Это не приговор — у капиталоёмких и заёмных бизнес-моделей так "
        "бывает штатно, но структуру обязательств стоит уточнить."
    )
    return _observed(
        "leverage", "Высокая доля обязательств в активах", detail, evidence
    )


CHECKS: tuple[FinanceCheck, ...] = (
    FinanceCheck("net_loss", "Убыток по итогам года", _check_net_loss),
    FinanceCheck(
        "revenue_decline", "Снижение выручки", _check_revenue_decline
    ),
    FinanceCheck(
        "liquidity_gap",
        "Покрытие краткосрочных обязательств",
        _check_liquidity_gap,
    ),
    FinanceCheck(
        "negative_equity", "Отрицательный капитал", _check_negative_equity
    ),
    FinanceCheck("leverage", "Доля обязательств в активах", _check_leverage),
)


def run_checks(view: FinanceView) -> list[Observation]:
    """Runs every check and returns the observations that fired."""
    observations: list[Observation] = []
    for check in CHECKS:
        observation = check.run(view)
        if observation is not None:
            observations.append(observation)
    return observations
