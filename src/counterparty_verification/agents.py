from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openrouter import OpenRouterModel
from pydantic_ai.providers.openrouter import OpenRouterProvider

from .domain import (
    AnalysisSummary,
    ChapterResult,
    CounterpartyCard,
    Evidence,
    FactorSummaryItem,
    Observation,
    RiskLevel,
)
from .prompt_constants import (
    EVALUATOR_INSTRUCTIONS,
    QUESTION_ANSWER_INSTRUCTIONS,
    REPUTATION_AGGREGATOR_INSTRUCTIONS,
    SPECIALIST_INSTRUCTIONS,
)
from .reputation_rules import ReputationView
from .settings import Settings, get_settings


class GroundedText(BaseModel):
    text: str = Field(
        max_length=500,
        description="Краткий текст без названий полей, JSON и описания процесса проверки",
    )
    evidence_fields: list[str] = Field(
        default_factory=list,
        description="Точные пути полей для машинной проверки; не включать их в text",
    )


class EvaluatorStatement(BaseModel):
    text: str = Field(
        max_length=300,
        description="Одно короткое утверждение о существенном факте без вводных фраз",
    )
    fact_ids: list[str] = Field(
        min_length=1,
        description="Идентификаторы фактов, подтверждающих утверждение",
    )


class EvaluatorOutput(BaseModel):
    statements: list[EvaluatorStatement] = Field(min_length=2, max_length=3)


def _model(settings: Settings) -> OpenRouterModel:
    if not settings.openrouter_api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not configured")
    return OpenRouterModel(
        settings.openrouter_model,
        provider=OpenRouterProvider(api_key=settings.openrouter_api_key),
    )


def _chapter_fields(chapter: ChapterResult) -> set[str]:
    fields = {item.field for item in chapter.evidence}
    for factor in chapter.factors:
        fields.update(item.field for item in factor.evidence)
    for observation in chapter.observations:
        fields.update(item.field for item in observation.evidence)
    return fields


def flatten_field_paths(value: Any, prefix: str = "") -> set[str]:
    paths: set[str] = set()
    if isinstance(value, dict):
        for key, nested in value.items():
            path = f"{prefix}.{key}" if prefix else key
            paths.add(path)
            paths.update(flatten_field_paths(nested, path))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            path = f"{prefix}[{index}]"
            paths.add(path)
            paths.update(flatten_field_paths(nested, path))
    return paths


class SpecialistAgent:
    def __init__(self, settings: Settings) -> None:
        self.enabled = bool(settings.openrouter_api_key)
        self.agent = (
            Agent(
                _model(settings),
                output_type=GroundedText,

                instructions=SPECIALIST_INSTRUCTIONS,

            )
            if self.enabled
            else None
        )

    async def enrich(self, chapter: ChapterResult) -> ChapterResult:
        if not self.agent:
            return chapter
        payload = {
            "task": (
                "Кратко переформулируй готовое заключение, не меняя его смысл."
            ),
            "chapter": chapter.model_dump(mode="json"),
        }
        result = await self.agent.run(json.dumps(payload, ensure_ascii=False))
        allowed = _chapter_fields(chapter)
        if result.output.evidence_fields and set(
            result.output.evidence_fields
        ).issubset(allowed):
            chapter.conclusion = result.output.text
        return chapter


class EvaluatorAgent:
    def __init__(self, settings: Settings) -> None:
        self.enabled = bool(settings.openrouter_api_key)
        self.agent = (
            Agent(
                _model(settings),
                output_type=EvaluatorOutput,

                instructions=EVALUATOR_INSTRUCTIONS,

            )
            if self.enabled
            else None
        )

    async def summarize(
        self,
        company_name: str,
        risk_level: RiskLevel,
        factors: list[FactorSummaryItem],
    ) -> AnalysisSummary:
        if not self.agent:
            raise RuntimeError("OPENROUTER_API_KEY is not configured")

        risk_labels = {
            RiskLevel.LOW: "Низкий риск",
            RiskLevel.MEDIUM: "Средний риск",
            RiskLevel.HIGH: "Высокий риск",
            RiskLevel.UNKNOWN: "Уровень риска не определён",
        }
        facts = [
            {
                "id": f"{factor.chapter}.{index}",
                "section": factor.label,
                "status": factor.status.value,
                "text": detail,
            }
            for factor in factors
            for index, detail in enumerate(factor.details, start=1)
        ]
        if not facts:
            raise RuntimeError("No report facts available for summary")

        payload = {
            "task": "Составь ёмкое объяснение уровня риска для пользователя.",
            "company": company_name,
            "risk_label": risk_labels[risk_level],
            "facts": facts,
        }
        result = await self.agent.run(json.dumps(payload, ensure_ascii=False))
        allowed = {fact["id"] for fact in facts}
        if any(
            not set(statement.fact_ids).issubset(allowed)
            for statement in result.output.statements
        ):
            raise RuntimeError("Summary contains unknown fact identifiers")

        used_ids = {
            fact_id
            for statement in result.output.statements
            for fact_id in statement.fact_ids
        }
        facts_by_id = {fact["id"]: fact["text"] for fact in facts}
        summary_text = " ".join(item.text for item in result.output.statements)
        return AnalysisSummary(
            risk_level=risk_level,
            summary=summary_text,
            key_factors=[
                facts_by_id[fact_id]
                for fact_id in facts_by_id
                if fact_id in used_ids
            ][:5],
        )


class QuestionAnswerAgent:
    def __init__(self, settings: Settings) -> None:
        self.enabled = bool(settings.openrouter_api_key)
        self.agent = (
            Agent(
                _model(settings),
                output_type=GroundedText,

                instructions=QUESTION_ANSWER_INSTRUCTIONS,

            )
            if self.enabled
            else None
        )

    async def answer(
        self,
        question: str,
        card: CounterpartyCard,
        chapters: list[ChapterResult],
    ) -> str:
        if not self.agent:
            return (
                "OpenRouter не настроен, поэтому диалоговый ответ недоступен. "
                "Исходный анализ сформирован детерминированно."
            )
        payload = {
            "task": "Ответь на вопрос по данным отчёта.",
            "question": question,
            "card": card.model_dump(mode="json"),
            "analysis": [item.model_dump(mode="json") for item in chapters],
        }
        result = await self.agent.run(json.dumps(payload, ensure_ascii=False))
        allowed = flatten_field_paths(payload["card"])
        citations = set(result.output.evidence_fields)
        if citations and not citations.issubset(allowed):
            return "В предоставленных данных нет подтверждения для ответа."
        if not citations:
            return "В предоставленных данных нет ответа на этот вопрос."
        return result.output.text


class ReputationHighlight(BaseModel):
    chapter: str
    title: str
    text: str
    evidence_fields: list[str] = Field(default_factory=list)


class ReputationAggregateOutput(BaseModel):
    highlights: list[ReputationHighlight] = Field(default_factory=list)


class ReputationAgent:
    """Agent-as-tool: the LLM call that backs `analyze_reputation` itself.

    Unlike `SpecialistAgent`/`EvaluatorAgent`, this agent does not enrich an
    already-deterministic conclusion — it *is* the tool's aggregation logic
    for a chapter whose raw material is free-form text. Same grounding and
    evidence-validation discipline: no evidence, an unknown chapter, or a
    reference outside the card and the answer is rejected.
    """

    def __init__(self, settings: Settings) -> None:
        self.enabled = bool(settings.openrouter_api_key)
        self.agent = (
            Agent(
                _model(settings),
                output_type=ReputationAggregateOutput,
                instructions=REPUTATION_AGGREGATOR_INSTRUCTIONS,
            )
            if self.enabled
            else None
        )

    async def aggregate(self, view: ReputationView) -> list[Observation]:
        if not view.chapters:
            return []
        if not self.agent:
            raise RuntimeError("OPENROUTER_API_KEY is not configured")
        payload = {
            chapter: [
                {
                    "sign": entry.item.sign,
                    "code": entry.code,
                    "name": entry.item.name,
                    "field": entry.field("name"),
                }
                for entry in entries
            ]
            for chapter, entries in view.by_chapter.items()
        }
        result = await self.agent.run(json.dumps(payload, ensure_ascii=False))
        allowed = {entry.field("name") for entry in view.indexed}
        values = {entry.field("name"): entry.item.name for entry in view.indexed}
        highlights = result.output.highlights
        valid = bool(highlights) and all(
            highlight.chapter in view.chapters
            and highlight.evidence_fields
            and set(highlight.evidence_fields).issubset(allowed)
            for highlight in highlights
        )
        if not valid:
            raise RuntimeError("Reputation summary contains invalid evidence")
        return [
            Observation(
                code=f"chapter_{highlight.chapter}",
                title=highlight.title,
                detail=highlight.text,
                evidence=[
                    Evidence(field=field, value=values.get(field))
                    for field in highlight.evidence_fields
                ],
            )
            for highlight in highlights
        ]


@lru_cache
def get_reputation_agent() -> ReputationAgent:
    """Lazily-cached singleton: the only way to hand `Settings` to the
    reputation MCP tool, which otherwise takes just a `CounterpartyCard`
    (same pattern as `settings.get_settings`).
    """
    return ReputationAgent(get_settings())
