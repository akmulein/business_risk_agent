from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openrouter import OpenRouterModel
from pydantic_ai.providers.openrouter import OpenRouterProvider

from .domain import AnalysisSummary, ChapterResult, CounterpartyCard, RiskLevel
from .settings import Settings


SYSTEM_GROUNDING = """
You analyze exactly one counterparty. Use only the JSON supplied in the user
message. Never use general knowledge, web data, or assumptions. If a fact is
missing, state that the data is insufficient. Keep numbers and statuses exact.
Reply in Russian.
""".strip()


class GroundedText(BaseModel):
    text: str
    evidence_fields: list[str] = Field(default_factory=list)


class EvaluatorOutput(BaseModel):
    risk_level: RiskLevel
    statements: list[GroundedText]
    key_factors: list[str] = Field(default_factory=list)


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
                instructions=SYSTEM_GROUNDING
                + "\nRewrite the supplied deterministic chapter conclusion clearly.",
            )
            if self.enabled
            else None
        )

    async def enrich(self, chapter: ChapterResult) -> ChapterResult:
        if not self.agent:
            return chapter
        result = await self.agent.run(
            json.dumps(chapter.model_dump(mode="json"), ensure_ascii=False)
        )
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
                instructions=SYSTEM_GROUNDING
                + """
Aggregate all chapter results. Every statement must cite one or more exact
evidence field paths present in those chapter results. Do not invent a new risk
factor. Mention sections with insufficient data.
""",
            )
            if self.enabled
            else None
        )

    async def summarize(self, chapters: list[ChapterResult]) -> AnalysisSummary:
        if not self.agent:
            return self._deterministic_summary(chapters)
        result = await self.agent.run(
            json.dumps(
                [chapter.model_dump(mode="json") for chapter in chapters],
                ensure_ascii=False,
            )
        )
        allowed = set().union(*(_chapter_fields(item) for item in chapters))
        if not result.output.statements or any(
            not statement.evidence_fields
            or not set(statement.evidence_fields).issubset(allowed)
            for statement in result.output.statements
        ):
            return self._deterministic_summary(chapters)
        return AnalysisSummary(
            risk_level=result.output.risk_level,
            summary=" ".join(item.text for item in result.output.statements),
            key_factors=result.output.key_factors,
        )

    @staticmethod
    def _deterministic_summary(chapters: list[ChapterResult]) -> AnalysisSummary:
        rank = {
            RiskLevel.UNKNOWN: 0,
            RiskLevel.LOW: 1,
            RiskLevel.MEDIUM: 2,
            RiskLevel.HIGH: 3,
        }
        risk = max(
            (chapter.risk_level for chapter in chapters),
            key=rank.get,
            default=RiskLevel.UNKNOWN,
        )
        conclusions = " ".join(chapter.conclusion for chapter in chapters)
        factors = [
            factor.title for chapter in chapters for factor in chapter.factors
        ]
        return AnalysisSummary(
            risk_level=risk,
            summary=f"Итоговый уровень риска: {risk.value}. {conclusions}",
            key_factors=factors,
        )


class QuestionAnswerAgent:
    def __init__(self, settings: Settings) -> None:
        self.enabled = bool(settings.openrouter_api_key)
        self.agent = (
            Agent(
                _model(settings),
                output_type=GroundedText,
                instructions=SYSTEM_GROUNDING
                + """
Answer the question only from the card and analysis. Cite exact field paths.
If the answer is absent, say so and return no evidence fields.
""",
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
