import os

os.environ["OPENROUTER_API_KEY"] = ""

import pytest

from app.domain import CounterpartyCard


@pytest.fixture
def card() -> CounterpartyCard:
    """Small synthetic input shared by API and agent contract tests."""
    identity = {"report_id": "test-report", "company_inn": "7707083893"}
    return CounterpartyCard.model_validate(
        {
            "company_reports": {
                "report_id": "test-report",
                "inn": "7707083893",
                "short_name": "ООО Тестовая компания",
                "status": "CURRENT",
                "risk_level": "MEDIUM",
                "report_date": "2025-12-31",
            },
            "financial_reports": [
                {
                    **identity,
                    "year": 2025,
                    "proceeds": 1000000,
                    "profit": 100000,
                }
            ],
            "risk_factors": [
                {
                    **identity,
                    "sign": "positive",
                    "item_index": 0,
                    "name": "Сведения об адресе достоверны",
                    "chapter": "reestrs",
                }
            ],
        }
    )


@pytest.fixture
def repository(card):
    from tests.helpers import InMemoryRepository

    return InMemoryRepository([card])


@pytest.fixture(autouse=True)
def disable_live_llm(monkeypatch):
    from app.settings import get_settings

    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
