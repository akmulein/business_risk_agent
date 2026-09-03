import json
from pathlib import Path

import pytest

from counterparty_verification.domain import CounterpartyCard


@pytest.fixture
def card() -> CounterpartyCard:
    path = Path(__file__).parents[1] / "data" / "counterparties.json"
    return CounterpartyCard.model_validate(json.loads(path.read_text())[0])
