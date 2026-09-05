from counterparty_verification.domain import CounterpartyCard
from counterparty_verification.presentation import (
    build_factor_summary,
    build_visualization_data,
)


SOURCE_DETAILS = [
    (
        "Есть действующие исполнительные производства, в которых выступает в "
        "качестве ответчика, это может означать, что компания имеет неисполненные "
        "обязательства перед кредиторами или государственными органами. Такая "
        "информация негативно сказывается на репутации и кредитоспособности лица "
        "или организации, поскольку свидетельствует о возможных финансовых "
        "трудностях или нежелании выполнять свои обязательства."
    ),
    (
        "Компания имеет большое количество кодов ОКВЭД, что может быть связано "
        "с попыткой компании охватить как можно больше направлений бизнеса, это "
        "может отрицательно сказаться на ее эффективности и надежности."
    ),
    (
        "Есть арбитражные дела, в которых выступает в качестве ответчика, что "
        "может указывать на наличие споров с контрагентами или государственными "
        "органами. Это может быть признаком нестабильности в деятельности компании."
    ),
]


def _card() -> CounterpartyCard:
    return CounterpartyCard.model_validate(
        {
            "company_reports": {"report_id": "r-1", "inn": "1684017097"},
            "risk_factors": [
                {
                    "report_id": "r-1",
                    "company_inn": "1684017097",
                    "sign": "negative",
                    "item_index": index,
                    "name": detail,
                    "chapter": "reputation",
                }
                for index, detail in enumerate(SOURCE_DETAILS)
            ],
        }
    )


def test_factor_summary_uses_short_reputation_details() -> None:
    row = build_factor_summary(_card(), [])[0]

    assert row.details == [
        (
            "Есть действующие исполнительные производства, в которых выступает "
            "в качестве ответчика. Это негативно сказывается на репутации и "
            "кредитоспособности."
        ),
        (
            "Компания имеет большое количество кодов ОКВЭД, что может быть "
            "связано с попыткой компании охватить как можно больше направлений "
            "бизнеса."
        ),
        "Есть арбитражные дела, в которых выступает в качестве ответчика.",
    ]


def test_llm_context_keeps_full_factor_details() -> None:
    row = build_factor_summary(_card(), [], compact=False)[0]

    assert row.details == SOURCE_DETAILS


def test_visualizations_are_built_from_financial_and_legal_report_data() -> None:
    card = CounterpartyCard.model_validate(
        {
            "company_reports": {"report_id": "r-1", "inn": "1684017097"},
            "financial_reports": [
                {
                    "report_id": "r-1",
                    "company_inn": "1684017097",
                    "year": 2025,
                    "proceeds": 1_000,
                    "profit": 100,
                    "total_assets": 800,
                    "total_liabilities": 800,
                    "capitals": 300,
                    "long_term_duties_total": 200,
                    "short_term_liabilities_total": 300,
                }
            ],
            "arbitration": [
                {
                    "id": "court-1",
                    "report_id": "r-1",
                    "company_inn": "1684017097",
                    "source": "yearly",
                    "year": 2025,
                    "role": "defendant",
                    "case_status": "all",
                    "case_count": 3,
                }
            ],
            "legal_events": [
                {
                    "report_id": "r-1",
                    "company_inn": "1684017097",
                    "event_type": "execution",
                    "item_index": 0,
                    "event_date": "2025-04-10",
                },
                {
                    "report_id": "r-1",
                    "company_inn": "1684017097",
                    "event_type": "execution",
                    "item_index": 1,
                    "event_date": "2024-03-01",
                },
            ],
        }
    )

    result = build_visualization_data(card)

    assert result.financials[0].assets == 800
    assert result.financials[0].obligations == 500
    assert [item.model_dump() for item in result.legal_dynamics] == [
        {"year": 2024, "courts": 0, "enforcements": 1},
        {"year": 2025, "courts": 3, "enforcements": 1},
    ]
