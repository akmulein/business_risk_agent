from __future__ import annotations

from counterparty_verification.analysis.rules.reputation import (
    CHAPTER_LABELS,
    ReputationView,
)
from counterparty_verification.domain import Observation


def aggregate_reputation(view: ReputationView) -> list[Observation]:
    """Group source reputation factors by chapter -- no model call involved.

    `risk_factors` already arrives from the data provider as free-form text,
    pre-labelled with a sign (`negative`/`positive`) and a `chapter`, so there
    is nothing left to infer: each chapter's (deduplicated) factor texts are
    joined into one observation, with evidence pointing at the exact
    `risk_factors[i].name` fields they came from.
    """
    return [
        Observation(
            code=f"chapter_{chapter}",
            title=CHAPTER_LABELS.get(chapter, chapter),
            detail="; ".join(dict.fromkeys(entry.item.name for entry in entries)),
            evidence=[entry.evidence("name") for entry in entries],
        )
        for chapter, entries in view.by_chapter.items()
    ]
