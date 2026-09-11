import json
from pathlib import Path

import pytest

from counterparty_verification.domain import CounterpartyCard


@pytest.fixture
def card() -> CounterpartyCard:
    path = Path(__file__).parents[1] / "data" / "counterparties.json"
    return CounterpartyCard.model_validate(json.loads(path.read_text())[0])


@pytest.fixture(autouse=True)
def disable_live_llm(monkeypatch):
    from counterparty_verification.agents import get_reputation_agent
    from counterparty_verification.settings import get_settings

    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    get_reputation_agent.cache_clear()
    get_settings.cache_clear()
    yield
    get_reputation_agent.cache_clear()
    get_settings.cache_clear()
