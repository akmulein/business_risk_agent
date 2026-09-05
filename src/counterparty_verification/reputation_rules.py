"""Deterministic grouping for the reputational-risk chapter.

Unlike the legal and structure chapters, there are no thresholds to check
here: `risk_factors` already arrives from the data provider as free-form
Russian text, pre-labelled with a sign (`negative`/`positive`) and a
`chapter`. There is nothing left to detect — only to group, deduplicate and
highlight. The grouping built here (`ReputationView`) feeds an LLM agent
(`agents.ReputationAgent`) that does the actual aggregation; `
fallback_observations` is the deterministic safety net used when that agent
is disabled or its answer fails evidence validation, so the tool never
blocks and never invents a factor.

Described in `tools_rules/analyze_reputation.md` under the same
`chapter_<name>` codes reported in `Observation.code`.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from functools import cached_property

from .domain import CounterpartyCard, Evidence, Observation, SourceRiskFactor

# ---------------------------------------------------------------------------
# Dictionaries: the single place to tune wording and known data quirks.
# ---------------------------------------------------------------------------

# Human-readable Russian labels for the ten `chapter` values seen in the
# source data. An unknown chapter falls back to its raw code.
CHAPTER_LABELS: dict[str, str] = {
    "reestrs": "Реестры ФНС",
    "manager": "Руководитель",
    "arbitr": "Арбитраж",
    "finance": "Финансы",
    "okved": "ОКВЭД",
    "filials": "Филиалы",
    "site": "Сайт",
    "license": "Лицензии",
    "relatedComp": "Связанные компании",
    "execproc": "Исполнительные производства",
}

# Known data quirk: the source occasionally spells this code with a
# Cyrillic "а" in `positive[]`, while `negative[]` uses the Latin "a". Both
# mean the same factor, so they are normalized to one canonical code before
# grouping — otherwise they'd silently count as two different factors.
CODE_ALIASES: dict[str, str] = {
    "аrbitrationDefendant": "arbitrationDefendant",
}

# How many raw texts per chapter are handed to the LLM prompt, to keep the
# payload bounded regardless of how many factors a report carries.
MAX_ITEMS_PER_CHAPTER = 10


def _normalize_code(code: str | None) -> str | None:
    if code is None:
        return None
    return CODE_ALIASES.get(code, code)


# ---------------------------------------------------------------------------
# Indexed access to the card
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class IndexedRiskFactor:
    """Risk-factor row together with its position in `card.risk_factors`.

    The position builds evidence paths such as `risk_factors[2].name`, which
    are validated against the card by `agents.flatten_field_paths`.
    """

    index: int
    item: SourceRiskFactor

    def field(self, name: str) -> str:
        return f"risk_factors[{self.index}].{name}"

    def evidence(self, name: str = "name") -> Evidence:
        return Evidence(field=self.field(name), value=getattr(self.item, name, None))

    @property
    def code(self) -> str | None:
        return _normalize_code(self.item.code)

    @property
    def chapter(self) -> str:
        return self.item.chapter or "unknown"

    @property
    def label(self) -> str:
        return CHAPTER_LABELS.get(self.chapter, self.chapter)


@dataclass
class ReputationView:
    """Read-only projection of `card.risk_factors`, prepared once."""

    card: CounterpartyCard

    @cached_property
    def indexed(self) -> list[IndexedRiskFactor]:
        return [
            IndexedRiskFactor(index=index, item=item)
            for index, item in enumerate(self.card.risk_factors)
        ]

    @cached_property
    def negative(self) -> list[IndexedRiskFactor]:
        return [entry for entry in self.indexed if entry.item.sign == "negative"]

    @cached_property
    def positive(self) -> list[IndexedRiskFactor]:
        return [entry for entry in self.indexed if entry.item.sign == "positive"]

    @cached_property
    def by_chapter(self) -> dict[str, list[IndexedRiskFactor]]:
        grouped: dict[str, list[IndexedRiskFactor]] = defaultdict(list)
        for entry in self.indexed:
            grouped[entry.chapter].append(entry)
        return dict(grouped)

    @cached_property
    def chapters(self) -> list[str]:
        """Chapters present in the card, in order of first appearance."""
        seen: list[str] = []
        for entry in self.indexed:
            if entry.chapter not in seen:
                seen.append(entry.chapter)
        return seen


def build_view(card: CounterpartyCard) -> ReputationView:
    return ReputationView(card=card)


# ---------------------------------------------------------------------------
# Deterministic fallback
# ---------------------------------------------------------------------------


def _chapter_detail(entries: list[IndexedRiskFactor]) -> str:
    negative = [entry.item.name for entry in entries if entry.item.sign == "negative"]
    positive = [entry.item.name for entry in entries if entry.item.sign == "positive"]
    parts: list[str] = []
    if negative:
        parts.append(f"Негативные: {'; '.join(negative)}")
    if positive:
        parts.append(f"Позитивные: {'; '.join(positive)}")
    return " ".join(parts)


def fallback_observations(view: ReputationView) -> list[Observation]:
    """Groups the raw texts by chapter, verbatim, without any LLM call.

    Used when the aggregation agent is disabled or its answer fails
    evidence validation: the tool must still return something, and it must
    never paraphrase or judge on its own.
    """
    observations: list[Observation] = []
    for chapter in view.chapters:
        entries = view.by_chapter[chapter]
        observations.append(
            Observation(
                code=f"chapter_{chapter}",
                title=CHAPTER_LABELS.get(chapter, chapter),
                detail=_chapter_detail(entries),
                evidence=[entry.evidence("name") for entry in entries],
            )
        )
    return observations
