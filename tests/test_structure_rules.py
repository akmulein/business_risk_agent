from pathlib import Path
from typing import Any

import pytest

from counterparty_verification.agents import flatten_field_paths
from counterparty_verification.analyzers import analyze_structure
from counterparty_verification.domain import CounterpartyCard, Observation, RiskLevel
from counterparty_verification.structure_rules import CHECKS

RULES_DOC = Path(__file__).parents[1] / "tools_rules" / "analyze_structure.md"

COMPANY_REPORT: dict[str, Any] = {
    "report_id": "r-1",
    "report_date": "2026-01-01",
    "inn": "1684017097",
    "ogrn": "1241600001048",
    "short_name": 'ООО "ТЕСТ"',
    "full_name": 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ТЕСТ"',
    "registration_date": "2015-01-01",
    "years_from_registration": 11,
    "status": "CURRENT",
    "share_capital": 1_000_000,
    "email": "test@test.invalid",
}


def _item(item_type: str, index: int, **fields: Any) -> dict[str, Any]:
    return {
        "id": f"{item_type}-{index}",
        "report_id": "r-1",
        "company_inn": "1684017097",
        "item_type": item_type,
        "item_index": index,
        **fields,
    }


def _card(items: list[dict[str, Any]], **report: Any) -> CounterpartyCard:
    return CounterpartyCard.model_validate(
        {
            "company_reports": {**COMPANY_REPORT, **report},
            "structure_items": items,
        }
    )


def _observed(card: CounterpartyCard) -> dict[str, Observation]:
    return {item.code: item for item in analyze_structure(card).observations}


def _director(**fields: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "name": "ИВАНОВ ИВАН ИВАНОВИЧ",
        "related_inn": "130801590508",
        "position": "ГЕНЕРАЛЬНЫЙ ДИРЕКТОР",
    }
    return _item("director", 0, **{**defaults, **fields})


def _founder(index: int = 0, **fields: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "name": "ИВАНОВ ИВАН ИВАНОВИЧ",
        "related_inn": "130801590508",
        "role": "founder",
        "share": 100,
        "amount": 1_000_000,
        "active": True,
    }
    return _item("founder", index, **{**defaults, **fields})


def test_chapter_never_grades_the_counterparty() -> None:
    card = _card([_director(position="КОНКУРСНЫЙ УПРАВЛЯЮЩИЙ")])

    result = analyze_structure(card)

    assert result.risk_level == RiskLevel.UNKNOWN
    assert not result.factors
    assert "director_authority" in _observed(card)


def test_bankruptcy_manager_as_director_is_observed() -> None:
    card = _card([_director(position="КОНКУРСНЫЙ УПРАВЛЯЮЩИЙ")])

    assert "КОНКУРСНЫЙ УПРАВЛЯЮЩИЙ" in _observed(card)["director_authority"].detail


def test_company_without_director_is_observed() -> None:
    card = _card([_founder()])

    assert "director_authority" in _observed(card)


def test_recent_appointment_is_observed_with_the_day_count() -> None:
    recent = _card([_director(date_from="2025-12-01T21:00:00.000Z")])
    older = _card([_director(date_from="2025-04-01T21:00:00.000Z")])
    ancient = _card([_director(date_from="2016-01-01T21:00:00.000Z")])

    assert "31 дней" in _observed(recent)["director_change"].detail
    assert "director_change" in _observed(older)
    assert "director_change" not in _observed(ancient)


def test_share_sum_above_one_hundred_is_reported() -> None:
    card = _card(
        [
            _founder(0, share=100, amount=1_000_000),
            _founder(
                1,
                share=100,
                amount=1_000_000,
                name="ПЕТРОВ ПЕТР ПЕТРОВИЧ",
                related_inn="530202122011",
            ),
            _director(),
        ]
    )

    assert "200%" in _observed(card)["ownership_integrity"].detail


def test_sole_trader_does_not_produce_ownership_findings() -> None:
    card = _card(
        [_item("activity", 0, role="main", code="70.22", description="Консультирование")],
        inn="120705254031",
        ogrn="325774600178399",
        short_name="ИП ПАВЛИЧУК Р.В.",
        full_name="ПАВЛИЧУК РОМАН ВИКТОРОВИЧ",
        share_capital=None,
    )

    result = analyze_structure(card)

    assert result.data_sufficient
    assert not {
        "ownership_integrity",
        "ownership_chain",
        "shell_pattern",
        "director_authority",
    } & _observed(card).keys()
    assert "индивидуальный предприниматель" in result.conclusion


def test_director_of_three_related_companies_is_observed() -> None:
    related = [
        _item(
            "related_company",
            index,
            name=f'ООО "СВЯЗЬ-{index}"',
            related_inn=f"78132347{index}0",
            auth_person_name="Иванов Иван Иванович",
            auth_person_position="ДИРЕКТОР",
        )
        for index in range(3)
    ]
    card = _card([_director(), *related])

    detail = _observed(card)["mass_director"].detail
    assert "ещё в 3" in detail
    assert "массовое руководство" in detail


def test_related_company_of_the_owner_is_affiliation() -> None:
    card = _card(
        [
            _founder(),
            _director(),
            _item(
                "related_company",
                0,
                name="ИП ИВАНОВ ИВАН ИВАНОВИЧ",
                related_inn="130801590508",
            ),
        ]
    )

    assert "105.1" in _observed(card)["affiliation"].detail


def test_corporate_founder_requires_ownership_chain() -> None:
    card = _card(
        [
            _founder(name='ООО "МАТЬ"', related_inn="7813664770"),
            _director(),
        ]
    )

    assert "ownership_chain" in _observed(card)


def test_many_activity_codes_are_reported() -> None:
    activities = [_item("activity", 0, role="main", code="46.90")] + [
        _item("activity", index, role="other", code=f"47.{index}")
        for index in range(1, 25)
    ]
    card = _card([_director(), *activities])

    assert "24" in _observed(card)["okved_breadth"].detail


def test_permit_is_matched_by_the_main_activity_only() -> None:
    main_needs_permit = _card(
        [_director(), _item("activity", 0, role="main", code="86.21", name="Врачебная практика")]
    )
    secondary_only = _card(
        [
            _director(),
            _item("activity", 0, role="main", code="70.22", name="Консультирование"),
            _item("activity", 1, role="other", code="86.21", name="Врачебная практика"),
        ]
    )
    with_license = CounterpartyCard.model_validate(
        {
            "company_reports": COMPANY_REPORT,
            "structure_items": [
                _director(),
                _item("activity", 0, role="main", code="86.21", name="Врачебная практика"),
            ],
            "legal_events": [
                {
                    "report_id": "r-1",
                    "company_inn": "1684017097",
                    "event_type": "license",
                    "item_index": 0,
                    "status": "ACTIVE",
                    "title": "Медицинская лицензия",
                }
            ],
        }
    )

    assert "license_gap" in _observed(main_needs_permit)
    assert "license_gap" not in _observed(secondary_only)
    assert "license_gap" not in _observed(with_license)


def test_shell_pattern_needs_three_signals() -> None:
    two_signals = _card(
        [_founder(), _director()],
        share_capital=10_000,
        company_size="Средние предприятия",
    )
    many_signals = _card(
        [_founder(), _director()],
        share_capital=10_000,
        years_from_registration=1,
        company_size="Микропредприятие",
        email=None,
    )

    assert "shell_pattern" not in _observed(two_signals)
    detail = _observed(many_signals)["shell_pattern"].detail
    assert "минимальный уставный капитал" in detail
    assert "5 формальных признаков" in detail


def test_quiet_company_produces_no_observations() -> None:
    card = _card(
        [
            _founder(0, share=60, amount=600_000),
            _founder(
                1,
                share=40,
                amount=400_000,
                name="ПЕТРОВ ПЕТР ПЕТРОВИЧ",
                related_inn="530202122011",
            ),
            _director(date_from="2016-01-01T21:00:00.000Z"),
            _item("activity", 0, role="main", code="70.22", description="Консультирование"),
        ],
        company_size="Средние предприятия",
    )

    result = analyze_structure(card)

    assert not result.observations
    assert "не найдено" in result.conclusion


def test_every_evidence_path_exists_in_the_card(card: CounterpartyCard) -> None:
    allowed = flatten_field_paths(card.model_dump(mode="json"))
    result = analyze_structure(card)

    paths = {item.field for item in result.evidence}
    for observation in result.observations:
        paths.update(item.field for item in observation.evidence)

    assert paths
    assert paths <= allowed


@pytest.mark.parametrize("check", CHECKS, ids=lambda check: check.code)
def test_every_check_is_documented(check) -> None:
    assert f"`{check.code}`" in RULES_DOC.read_text(encoding="utf-8")


def test_check_codes_are_unique() -> None:
    codes = [check.code for check in CHECKS]

    assert len(codes) == len(set(codes))
    assert len(codes) == 10
