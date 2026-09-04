"""Deterministic checks for the founders, management and structure chapter.

Ten checks, described in `tools_rules/analyze_structure.md` under the same names
that they report in `Observation.code`. A check never grades the counterparty: it
only states what deserves attention and points at the fields it read. No check
calls an LLM, the network or an external registry, so the same card always
produces the same result.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from functools import cached_property
from typing import Any

from .domain import (
    CompanyReport,
    CounterpartyCard,
    Evidence,
    Observation,
    StructureItem,
)

# ---------------------------------------------------------------------------
# Thresholds and dictionaries: the single place to tune the checks with experts.
# ---------------------------------------------------------------------------

MIN_SHARE_CAPITAL = 10_000.0
LOW_SHARE_CAPITAL = 100_000.0
SHARE_SUM_TOLERANCE = 1.0
AMOUNT_SUM_TOLERANCE = 1.0
CONTROL_SHARE_THRESHOLD = 99.5
AFFILIATION_SHARE_THRESHOLD = 20.0
RECENT_CHANGE_DAYS = 90
RECENT_APPOINTMENT_DAYS = 365
MANY_RELATED_COMPANIES = 3
MASS_OKVED_WARN = 20
MASS_OKVED_HIGH = 50
YOUNG_COMPANY_YEARS = 1
SHELL_PATTERN_MIN_SIGNALS = 3

TERMINATION_POSITIONS = (
    "ЛИКВИДАТОР",
    "КОНКУРСНЫЙ УПРАВЛЯЮЩИЙ",
    "ВНЕШНИЙ УПРАВЛЯЮЩИЙ",
    "АРБИТРАЖНЫЙ УПРАВЛЯЮЩИЙ",
    "ВРЕМЕННЫЙ УПРАВЛЯЮЩИЙ",
    "АДМИНИСТРАТИВНЫЙ УПРАВЛЯЮЩИЙ",
    "ЛИКВИДАЦИОННОЙ КОМИССИИ",
)

NON_PROFIT_MARKERS = (
    "АНО",
    "ГСК",
    "ТСЖ",
    "ТСН",
    "СНТ",
    "НКО",
    "ФОНД",
    "АССОЦИАЦИЯ",
    "СОЮЗ",
    "КООПЕРАТИВ",
    "ПАРТНЕРСТВО",
    "УЧРЕЖДЕНИЕ",
    "ОБЩИНА",
    "ПАЛАТА",
)

# Only the main activity is matched against this list: a company with dozens of
# secondary codes almost always touches one of these groups by accident.
PERMIT_REQUIRED_MAIN_OKVED = {
    "19": "лицензия на производство нефтепродуктов",
    "38": "лицензия на обращение с отходами",
    "41": "членство в СРО для строительства зданий",
    "43": "членство в СРО для специализированных строительных работ",
    "46.17": "лицензия на оборот алкоголя",
    "46.34": "лицензия на оборот алкоголя",
    "47.25": "лицензия на розничную продажу алкоголя",
    "49.3": "лицензия на перевозку пассажиров",
    "51": "лицензия на воздушные перевозки",
    "61": "лицензия на услуги связи",
    "65": "лицензия на страховую деятельность",
    "66": "лицензия на финансовое посредничество",
    "85": "лицензия на образовательную деятельность",
    "86": "лицензия на медицинскую деятельность",
}

PROVIDER_FLAG_CODES = (
    "invalidAuthpersonsData",
    "disqualifiedAuthpersons",
    "massAuthpersons",
    "invalidRegistrationData",
)

LICENSE_INACTIVE_MARKERS = ("EXPIRED", "АННУЛИР", "ПРЕКРАЩ", "ИСТЕК")
MICRO_COMPANY_MARKER = "МИКРО"
LEGAL_ENTITY_INN_LENGTH = 10
SOLE_TRADER_INN_LENGTH = 12
SOLE_TRADER_OGRN_LENGTH = 15

_NAME_SUFFIXES = ("ОГЛЫ", "КЫЗЫ", "ГЫЗЫ", "УУЛУ")


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def as_date(value: Any) -> date | None:
    """Source dates arrive as ISO strings with time, e.g. 2024-01-14T21:00:00Z."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        pass
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float, Decimal)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip().replace(" ", "").replace(",", "."))
        except ValueError:
            return None
    return None


def normalize_name(value: str | None) -> str:
    """Upper case, ё to е, drop patronymic suffixes and punctuation."""
    if not value:
        return ""
    text = str(value).upper().replace("Ё", "Е")
    text = re.sub(r"[^А-ЯA-Z]+", " ", text)
    return " ".join(token for token in text.split() if token not in _NAME_SUFFIXES)


def _json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _days_between(left: date | None, right: date | None) -> int | None:
    if left is None or right is None:
        return None
    return (left - right).days


class LegalForm(StrEnum):
    COMPANY = "COMPANY"
    SOLE_TRADER = "SOLE_TRADER"
    NON_PROFIT = "NON_PROFIT"


# ---------------------------------------------------------------------------
# Indexed access to the card
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class IndexedItem:
    """Structure row together with its position in `card.structure_items`.

    The position builds evidence paths such as `structure_items[3].share`, which
    are validated against the card by `agents.flatten_field_paths`.
    """

    index: int
    item: StructureItem

    def field(self, name: str) -> str:
        return f"structure_items[{self.index}].{name}"

    def evidence(self, name: str) -> Evidence:
        return Evidence(
            field=self.field(name),
            value=_json_value(getattr(self.item, name, None)),
        )

    @property
    def inn(self) -> str | None:
        return (self.item.related_inn or "").strip() or None

    @property
    def date_from(self) -> date | None:
        return as_date(self.item.date_from)

    @property
    def label(self) -> str:
        return self.item.name or self.inn or "без наименования"


@dataclass
class StructureView:
    """Read-only projection of the card, prepared once for all checks."""

    card: CounterpartyCard

    @cached_property
    def report(self) -> CompanyReport:
        return self.card.company_reports

    @cached_property
    def indexed(self) -> dict[str, list[IndexedItem]]:
        grouped: dict[str, list[IndexedItem]] = defaultdict(list)
        for index, item in enumerate(self.card.structure_items):
            grouped[item.item_type].append(IndexedItem(index=index, item=item))
        return grouped

    def of_type(self, item_type: str) -> list[IndexedItem]:
        return self.indexed.get(item_type, [])

    # -- organization ------------------------------------------------------

    @cached_property
    def legal_form(self) -> LegalForm:
        ogrn = (self.report.ogrn or "").strip()
        inn = (self.report.inn or "").strip()
        if len(ogrn) == SOLE_TRADER_OGRN_LENGTH or len(inn) == SOLE_TRADER_INN_LENGTH:
            return LegalForm.SOLE_TRADER
        name = normalize_name(self.report.short_name or self.report.full_name)
        if any(marker in name for marker in NON_PROFIT_MARKERS):
            return LegalForm.NON_PROFIT
        return LegalForm.COMPANY

    @cached_property
    def is_company(self) -> bool:
        return self.legal_form is LegalForm.COMPANY

    @cached_property
    def report_date(self) -> date:
        return as_date(self.report.report_date) or datetime.now(UTC).date()

    @cached_property
    def share_capital(self) -> float | None:
        return as_float(self.report.share_capital)

    # -- structure blocks --------------------------------------------------

    @cached_property
    def founders(self) -> list[IndexedItem]:
        return self.of_type("founder")

    @cached_property
    def active_founders(self) -> list[IndexedItem]:
        return [entry for entry in self.founders if entry.item.active is not False]

    @cached_property
    def director(self) -> IndexedItem | None:
        directors = self.of_type("director")
        return directors[0] if directors else None

    @cached_property
    def parents(self) -> list[IndexedItem]:
        return self.of_type("parent_organization")

    @cached_property
    def related(self) -> list[IndexedItem]:
        return self.of_type("related_company")

    @cached_property
    def activities(self) -> list[IndexedItem]:
        return self.of_type("activity")

    @cached_property
    def main_activity(self) -> IndexedItem | None:
        return next(
            (entry for entry in self.activities if entry.item.role == "main"), None
        )

    @cached_property
    def other_activities(self) -> list[IndexedItem]:
        return [entry for entry in self.activities if entry.item.role != "main"]

    @cached_property
    def branches(self) -> list[IndexedItem]:
        return self.of_type("branch")

    @cached_property
    def phones(self) -> list[IndexedItem]:
        return self.of_type("phone")

    @cached_property
    def tax_systems(self) -> list[IndexedItem]:
        return self.of_type("tax_system")

    # -- derived sets ------------------------------------------------------

    @cached_property
    def founder_inns(self) -> set[str]:
        return {entry.inn for entry in self.active_founders if entry.inn}

    @cached_property
    def person_inns(self) -> set[str]:
        inns = set(self.founder_inns)
        if self.director and self.director.inn:
            inns.add(self.director.inn)
        return inns

    @cached_property
    def related_inns(self) -> set[str]:
        return {entry.inn for entry in self.related if entry.inn}

    @cached_property
    def total_active_share(self) -> float | None:
        shares = [
            as_float(entry.item.share) or 0.0
            for entry in self.active_founders
            if entry.item.share is not None
        ]
        return sum(shares) if shares else None

    @cached_property
    def mass_director_matches(self) -> list[IndexedItem]:
        """Related companies headed by a person with the same normalized name."""
        director_name = normalize_name(self.director.item.name) if self.director else ""
        if not director_name:
            return []
        return [
            entry
            for entry in self.related
            if normalize_name(entry.item.auth_person_name) == director_name
        ]

    @cached_property
    def provider_flags(self) -> dict[tuple[str, str], int]:
        """Maps (sign, code) to the row index in `card.risk_factors`."""
        return {
            (item.sign, item.code or ""): index
            for index, item in enumerate(self.card.risk_factors)
        }

    @cached_property
    def has_active_license(self) -> bool:
        for event in self.card.legal_events:
            if event.event_type != "license":
                continue
            if any(
                marker in (event.status or "").upper()
                for marker in LICENSE_INACTIVE_MARKERS
            ):
                continue
            end_date = as_date(event.end_date)
            if end_date is None or end_date >= self.report_date:
                return True
        return False

    @cached_property
    def single_owner_is_director(self) -> bool:
        if len(self.active_founders) != 1 or self.director is None:
            return False
        founder = self.active_founders[0]
        share = as_float(founder.item.share)
        return (
            share is not None
            and share >= CONTROL_SHARE_THRESHOLD
            and bool(founder.inn)
            and founder.inn == self.director.inn
        )


def build_view(card: CounterpartyCard) -> StructureView:
    return StructureView(card=card)


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class StructureCheck:
    code: str
    title: str
    run: Callable[[StructureView], Observation | None]
    company_only: bool = False


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


def _activity_name(entry: IndexedItem) -> str:
    return entry.item.description or entry.item.name or "название не указано"


def _report_evidence(view: StructureView, *names: str) -> list[Evidence]:
    return [
        Evidence(
            field=f"company_reports.{name}",
            value=_json_value(getattr(view.report, name, None)),
        )
        for name in names
    ]


def _provider_evidence(view: StructureView, index: int) -> Evidence:
    return Evidence(
        field=f"risk_factors[{index}].name",
        value=view.card.risk_factors[index].name,
    )


def _check_director_authority(view: StructureView) -> Observation | None:
    """Кто вправе подписать договор и не идёт ли процедура банкротства."""
    director = view.director
    if director is None:
        # For a sole trader the individual acts in person, so nothing is missing.
        if view.parents or not view.is_company:
            return None
        return _observed(
            "director_authority",
            "В отчёте не указан единоличный исполнительный орган",
            "Нет сведений ни о руководителе, ни об управляющей организации, "
            "поэтому по отчёту не видно, кто вправе подписывать договор без "
            "доверенности. Запросите выписку ЕГРЮЛ и документ о назначении.",
            _report_evidence(view, "inn", "full_name"),
        )
    position = (director.item.position or "").upper()
    if not any(marker in position for marker in TERMINATION_POSITIONS):
        return None
    return _observed(
        "director_authority",
        "Руководитель — арбитражный управляющий или ликвидатор",
        f"Должность руководителя: «{director.item.position}». Такая должность "
        "появляется при процедуре банкротства или ликвидации, при этом статус "
        f"организации в отчёте указан как «{view.report.status or 'не указан'}». "
        "Стоит проверить дело о банкротстве и полномочия подписанта.",
        [
            director.evidence("position"),
            director.evidence("name"),
            *_report_evidence(view, "status", "status_reason"),
        ],
    )


def _check_director_change(view: StructureView) -> Observation | None:
    """Свежесть назначения руководителя относительно даты отчёта."""
    director = view.director
    if director is None or director.date_from is None:
        return None
    days = _days_between(view.report_date, director.date_from)
    if days is None or days < 0 or days > RECENT_APPOINTMENT_DAYS:
        return None
    recent = " Это меньше трёх месяцев до даты отчёта." if days <= RECENT_CHANGE_DAYS else ""
    return _observed(
        "director_change",
        "Руководитель сменился в течение последнего года",
        f"{director.item.name or 'Руководитель'} вступил в должность "
        f"{director.date_from.isoformat()}, за {days} дней до даты отчёта."
        f"{recent} Стоит уточнить причину смены и убедиться, что договор "
        "подписывает действующий руководитель.",
        [
            director.evidence("date_from"),
            director.evidence("name"),
            *_report_evidence(view, "report_date"),
        ],
    )


def _check_mass_director(view: StructureView) -> Observation | None:
    """Руководитель возглавляет связанные компании из того же отчёта."""
    matches = view.mass_director_matches
    if not matches or view.director is None:
        return None
    names = ", ".join(entry.label for entry in matches[:5])
    many = (
        " Это уже похоже на массовое руководство."
        if len(matches) >= MANY_RELATED_COMPANIES
        else ""
    )
    detail = (
        f"{view.director.item.name} значится руководителем ещё в {len(matches)} "
        f"связанных организациях: {names}.{many} Единого порога массовости у ФНС "
        "нет, поэтому это повод посмотреть, ведут ли эти компании реальную "
        "деятельность."
    )
    evidence = [
        view.director.evidence("name"),
        *(entry.evidence("auth_person_name") for entry in matches),
        *(entry.evidence("name") for entry in matches),
    ]
    positive = view.provider_flags.get(("positive", "massAuthpersons"))
    if positive is not None:
        detail += (
            " Поставщик данных при этом отнёс массовость директора к позитивным "
            "факторам — расхождение стоит сверить по реестрам ФНС."
        )
        evidence.append(_provider_evidence(view, positive))
    return _observed(
        "mass_director",
        "Руководитель возглавляет связанные организации",
        detail,
        evidence,
    )


def _check_provider_flags(view: StructureView) -> Observation | None:
    """Негативные флаги поставщика по руководству и регистрационным данным."""
    matched = [
        index
        for code in PROVIDER_FLAG_CODES
        if (index := view.provider_flags.get(("negative", code))) is not None
    ]
    if not matched:
        return None
    names = "; ".join(view.card.risk_factors[index].name for index in matched)
    return _observed(
        "provider_flags",
        "Отметки поставщика данных по руководству и регистрационным сведениям",
        f"В отчёте есть негативные отметки, относящиеся к руководству и "
        f"достоверности регистрационных данных: {names} Здесь они привязаны к "
        f"конкретному лицу: {view.director.item.name if view.director else 'руководитель не указан'}.",
        [_provider_evidence(view, index) for index in matched],
    )


def _check_ownership_integrity(view: StructureView) -> Observation | None:
    """Целостность сведений о составе участников и их долях."""
    problems: list[str] = []
    evidence: list[Evidence] = []
    if view.founders and not view.active_founders:
        problems.append("все перечисленные учредители помечены неактивными")
        evidence.extend(entry.evidence("active") for entry in view.founders)
    total_share = view.total_active_share
    if total_share is not None and abs(total_share - 100.0) > SHARE_SUM_TOLERANCE:
        problems.append(f"сумма долей активных учредителей равна {total_share:g}%")
        evidence.extend(
            entry.evidence("share")
            for entry in view.active_founders
            if entry.item.share is not None
        )
    capital = view.share_capital
    amounts = [
        entry for entry in view.active_founders if entry.item.amount is not None
    ]
    if capital is not None and amounts:
        total_amount = sum(as_float(entry.item.amount) or 0.0 for entry in amounts)
        if abs(total_amount - capital) > AMOUNT_SUM_TOLERANCE:
            problems.append(
                f"сумма долей в рублях ({total_amount:.0f} ₽) расходится с "
                f"уставным капиталом ({capital:.0f} ₽)"
            )
            evidence.extend(entry.evidence("amount") for entry in amounts)
            evidence.extend(_report_evidence(view, "share_capital"))
    if not problems:
        return None
    return _observed(
        "ownership_integrity",
        "Сведения о составе участников противоречивы",
        f"В данных о структуре владения есть расхождения: {'; '.join(problems)}. "
        "Это может быть и особенностью выгрузки, поэтому текущий состав "
        "участников стоит сверить с выпиской ЕГРЮЛ.",
        evidence,
    )


def _check_ownership_chain(view: StructureView) -> Observation | None:
    """Контроль вне компании: учредитель-юрлицо или управляющая организация."""
    corporate = [
        entry
        for entry in view.active_founders
        if entry.inn and len(entry.inn) == LEGAL_ENTITY_INN_LENGTH
    ]
    if not corporate and not view.parents:
        return None
    reasons: list[str] = []
    evidence: list[Evidence] = []
    if corporate:
        names = ", ".join(entry.label for entry in corporate)
        reasons.append(f"в состав участников входят организации ({names})")
        evidence.extend(entry.evidence("related_inn") for entry in corporate)
        evidence.extend(entry.evidence("name") for entry in corporate)
    if view.parents:
        names = ", ".join(entry.label for entry in view.parents)
        reasons.append(f"функции руководителя исполняет управляющая организация ({names})")
        evidence.extend(entry.evidence("name") for entry in view.parents)
        evidence.extend(entry.evidence("related_inn") for entry in view.parents)
    return _observed(
        "ownership_chain",
        "Конечный владелец по отчёту не виден",
        f"Контроль идёт через другие организации: {'; '.join(reasons)}. Отчёт "
        "раскрывает только первый уровень владения, поэтому структуру владения "
        "до физического лица стоит запросить у контрагента (обязанность знать "
        "своих бенефициаров закреплена 115-ФЗ).",
        evidence,
    )


def _check_affiliation(view: StructureView) -> Observation | None:
    """Связанные организации, принадлежащие тем же лицам."""
    own_related = [
        entry for entry in view.related if entry.inn and entry.inn in view.person_inns
    ]
    affiliated_founders = [
        entry
        for entry in view.active_founders
        if entry.inn
        and entry.inn in view.related_inns
        and (as_float(entry.item.share) or 0.0) >= AFFILIATION_SHARE_THRESHOLD
    ]
    if not own_related:
        return None
    names = ", ".join(entry.label for entry in own_related[:5])
    detail = (
        f"ИНН учредителя или руководителя совпадает с ИНН связанных организаций "
        f"({names}). Обычно за этим стоит собственное ИП или вторая компания того "
        "же лица. Само по себе это законно, но стоит понимать, кто из группы "
        "реально исполняет договор и куда уходит оборот."
    )
    if affiliated_founders:
        detail += (
            f" Доля таких участников в капитале не ниже "
            f"{AFFILIATION_SHARE_THRESHOLD:g}% — это признаки взаимозависимости "
            "по ст. 105.1 НК РФ."
        )
    evidence = [entry.evidence("related_inn") for entry in own_related]
    evidence += [entry.evidence("name") for entry in own_related]
    evidence += [entry.evidence("share") for entry in affiliated_founders]
    return _observed(
        "affiliation",
        "Связанные организации принадлежат учредителю или руководителю",
        detail,
        evidence,
    )


def _check_okved_breadth(view: StructureView) -> Observation | None:
    """Количество заявленных видов деятельности."""
    count = len(view.other_activities)
    provider = view.provider_flags.get(("negative", "massOkved"))
    if count <= MASS_OKVED_WARN and provider is None:
        return None
    main = (
        f"Основной вид деятельности — {view.main_activity.item.code} "
        f"«{_activity_name(view.main_activity)}». "
        if view.main_activity is not None and view.main_activity.item.code
        else ""
    )
    detail = f"{main}Дополнительных кодов ОКВЭД: {count}."
    if count > MASS_OKVED_HIGH:
        detail += (
            f" Это больше {MASS_OKVED_HIGH} кодов; такой разнородный набор часто "
            "означает, что коды заявлены «на всякий случай»."
        )
    detail += (
        " Стоит посмотреть, соответствует ли основной вид деятельности предмету "
        "сделки и какими кодами компания занимается фактически."
    )
    evidence = [entry.evidence("code") for entry in view.other_activities[:10]]
    if view.main_activity is not None:
        evidence.insert(0, view.main_activity.evidence("code"))
    if provider is not None:
        detail += " Поставщик данных также отметил массовость видов деятельности."
        evidence.append(_provider_evidence(view, provider))
    return _observed(
        "okved_breadth",
        "Много заявленных видов деятельности",
        detail,
        evidence,
    )


def _check_license_gap(view: StructureView) -> Observation | None:
    """Основной вид деятельности требует разрешения, а его нет в отчёте."""
    if view.has_active_license or view.main_activity is None:
        return None
    code = view.main_activity.item.code or ""
    if not code:
        return None
    permit = next(
        (
            name
            for prefix, name in PERMIT_REQUIRED_MAIN_OKVED.items()
            if code.startswith(prefix)
        ),
        None,
    )
    if permit is None:
        return None
    return _observed(
        "license_gap",
        "Основной вид деятельности требует разрешения, его нет в отчёте",
        f"Основной ОКВЭД {code} «{_activity_name(view.main_activity)}» обычно "
        f"требует {permit}, а действующих лицензий в отчёте не указано. Перечень "
        "укрупнённый, и конкретные работы контрагента могут разрешения не "
        "требовать, поэтому подтверждающие документы стоит просто запросить.",
        [
            view.main_activity.evidence("code"),
            view.main_activity.evidence("description"),
        ],
    )


def _check_shell_pattern(view: StructureView) -> Observation | None:
    """Совокупность слабых признаков технической компании."""
    signals: list[tuple[str, list[Evidence]]] = []
    capital = view.share_capital
    if capital is not None and capital <= MIN_SHARE_CAPITAL:
        signals.append(
            (
                f"минимальный уставный капитал ({capital:.0f} ₽)",
                _report_evidence(view, "share_capital"),
            )
        )
    elif capital is not None and capital <= LOW_SHARE_CAPITAL:
        signals.append(
            (
                f"низкий уставный капитал ({capital:.0f} ₽)",
                _report_evidence(view, "share_capital"),
            )
        )
    if view.single_owner_is_director:
        founder = view.active_founders[0]
        signals.append(
            (
                "единственный участник является руководителем",
                [founder.evidence("share"), founder.evidence("name")],
            )
        )
    years = view.report.years_from_registration
    if years is not None and years <= YOUNG_COMPANY_YEARS:
        signals.append(
            (
                f"компания зарегистрирована менее {YOUNG_COMPANY_YEARS + 1} лет назад",
                _report_evidence(view, "registration_date"),
            )
        )
    size = (view.report.company_size or "").upper()
    if size.startswith(MICRO_COMPANY_MARKER) and not view.branches:
        signals.append(
            (
                "микропредприятие без филиалов",
                _report_evidence(view, "company_size", "branches_count"),
            )
        )
    if not (view.report.email or view.report.website or view.phones):
        signals.append(
            (
                "нет ни телефона, ни e-mail, ни сайта",
                _report_evidence(view, "email", "website"),
            )
        )
    if len(view.other_activities) > MASS_OKVED_WARN:
        signals.append(
            (
                f"дополнительных кодов ОКВЭД {len(view.other_activities)}",
                [entry.evidence("code") for entry in view.other_activities[:5]],
            )
        )
    if len(signals) < SHELL_PATTERN_MIN_SIGNALS:
        return None
    listed = "; ".join(label for label, _ in signals)
    return _observed(
        "shell_pattern",
        "Компания небольшая по формальным признакам",
        f"Одновременно выполняются {len(signals)} формальных признаков: {listed}. "
        "Каждый из них по отдельности есть у множества добросовестных небольших "
        "компаний, поэтому это не вывод о фиктивности, а повод соотнести "
        "масштаб контрагента с суммой сделки и проверить ресурсы под её "
        "исполнение.",
        [evidence for _, group in signals for evidence in group],
    )


CHECKS: tuple[StructureCheck, ...] = (
    StructureCheck(
        "director_authority",
        "Полномочия руководителя",
        _check_director_authority,
    ),
    StructureCheck("director_change", "Смена руководителя", _check_director_change),
    StructureCheck(
        "mass_director",
        "Руководитель в связанных организациях",
        _check_mass_director,
    ),
    StructureCheck("provider_flags", "Отметки поставщика", _check_provider_flags),
    StructureCheck(
        "ownership_integrity",
        "Целостность сведений о долях",
        _check_ownership_integrity,
        company_only=True,
    ),
    StructureCheck(
        "ownership_chain",
        "Цепочка владения",
        _check_ownership_chain,
        company_only=True,
    ),
    StructureCheck("affiliation", "Аффилированность", _check_affiliation),
    StructureCheck("okved_breadth", "Виды деятельности", _check_okved_breadth),
    StructureCheck("license_gap", "Лицензии и разрешения", _check_license_gap),
    StructureCheck(
        "shell_pattern",
        "Масштаб компании",
        _check_shell_pattern,
        company_only=True,
    ),
)


def run_checks(view: StructureView) -> list[Observation]:
    """Runs every applicable check and returns the observations that fired."""
    observations: list[Observation] = []
    for check in CHECKS:
        if check.company_only and not view.is_company:
            continue
        observation = check.run(view)
        if observation is not None:
            observations.append(observation)
    return observations
