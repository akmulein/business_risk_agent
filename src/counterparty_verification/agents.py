from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openrouter import OpenRouterModel
from pydantic_ai.providers.openrouter import OpenRouterProvider

from .domain import AnalysisSummary, ChapterResult, CounterpartyCard, RiskLevel
from .llm_config import MODEL_SYSTEM_PROMPT
from .settings import Settings


class GroundedText(BaseModel):
    text: str = Field(
        max_length=500,
        description="Краткий текст без названий полей, JSON и описания процесса проверки",
    )
    evidence_fields: list[str] = Field(
        default_factory=list,
        description="Точные пути полей для машинной проверки; не включать их в text",
    )


class EvaluatorOutput(BaseModel):
    statements: list[GroundedText] = Field(min_length=1, max_length=5)
    key_factors: list[str] = Field(default_factory=list, max_length=5)


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
                instructions=MODEL_SYSTEM_PROMPT,
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
                instructions=MODEL_SYSTEM_PROMPT,
            )
            if self.enabled
            else None
        )

    async def summarize(self, chapters: list[ChapterResult]) -> AnalysisSummary:
        deterministic = self._deterministic_summary(chapters)
        if not self.agent:
            return deterministic
        payload = {
            "task": (
                "Составь краткое итоговое саммари. Не перечисляй все проверки и "
                "не добавляй новые факторы риска. Светофор уже рассчитан и не "
                "требует переоценки."
            ),
            "risk_level": deterministic.risk_level,
            "chapters": [chapter.model_dump(mode="json") for chapter in chapters],
        }
        result = await self.agent.run(json.dumps(payload, ensure_ascii=False))
        allowed = set().union(*(_chapter_fields(item) for item in chapters))
        if not result.output.statements or any(
            not statement.evidence_fields
            or not set(statement.evidence_fields).issubset(allowed)
            for statement in result.output.statements
        ):
            return deterministic
        return AnalysisSummary(
            risk_level=deterministic.risk_level,
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
                instructions=MODEL_SYSTEM_PROMPT,
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
