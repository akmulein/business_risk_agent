from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openrouter import OpenRouterModel

from .domain import (
    AnalysisSummary,
    ChapterResult,
    CounterpartyCard,
    Evidence,
    FactorSummaryItem,
    Observation,
    RiskLevel,
)
from .llm_provider import openrouter_provider
from .prompt_constants import (
    EVALUATOR_INSTRUCTIONS,
    QUESTION_ANSWER_INSTRUCTIONS,
    REPUTATION_AGGREGATOR_INSTRUCTIONS,
)
from .reputation_rules import CHAPTER_LABELS, ReputationView
from .settings import Settings, get_settings

logger = logging.getLogger(__name__)


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
        provider=openrouter_provider(settings.openrouter_api_key),
    )


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


class EvaluatorAgent:
    def __init__(self, settings: Settings) -> None:
        self.enabled = bool(settings.openrouter_api_key)
        self.agent = (
            Agent(
                _model(settings),
                output_type=EvaluatorOutput,
                model_settings={"temperature": 0},

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
        allowed = {fact["id"] for fact in facts}
        facts_by_id = {fact["id"]: fact["text"] for fact in facts}
        base_prompt = json.dumps(payload, ensure_ascii=False)
        last_error: Exception | None = None
        for attempt in range(1, 4):
            prompt = base_prompt
            if last_error is not None:
                prompt += (
                    "\n\nПредыдущий ответ не прошёл проверку. Используй только "
                    "точные id из facts и верни 2–3 коротких предложения."
                )
            try:
                logger.info(
                    "LLM call -> EvaluatorAgent.summarize facts=%d attempt=%d",
                    len(facts),
                    attempt,
                )
                result = await self.agent.run(prompt)
                if any(
                    not set(statement.fact_ids).issubset(allowed)
                    for statement in result.output.statements
                ):
                    raise RuntimeError(
                        "Summary contains unknown fact identifiers"
                    )
                used_ids = {
                    fact_id
                    for statement in result.output.statements
                    for fact_id in statement.fact_ids
                }
                logger.info(
                    "LLM call <- EvaluatorAgent.summarize attempt=%d", attempt
                )
                return AnalysisSummary(
                    risk_level=risk_level,
                    summary=" ".join(
                        item.text for item in result.output.statements
                    ),
                    key_factors=[
                        facts_by_id[fact_id]
                        for fact_id in facts_by_id
                        if fact_id in used_ids
                    ][:5],
                )
            except Exception as error:
                last_error = error
                logger.warning(
                    "Evaluator summary attempt %d failed: %s", attempt, error
                )
        raise RuntimeError(
            "Summary generation failed after 3 attempts"
        ) from last_error


class QuestionAnswerAgent:
    def __init__(self, settings: Settings) -> None:
        self.enabled = bool(settings.openrouter_api_key)
        self.agent = (
            Agent(
                _model(settings),
                output_type=GroundedText,
                model_settings={"temperature": 0},

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
            logger.info(
                "LLM call skipped (QuestionAnswerAgent.answer): agent disabled"
            )
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
        logger.info("LLM call -> QuestionAnswerAgent.answer")
        result = await self.agent.run(json.dumps(payload, ensure_ascii=False))
        logger.info("LLM call <- QuestionAnswerAgent.answer")
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
    """Summarize source factors, falling back to verbatim chapter groups.

    Only responses with nonempty, chapter-local evidence are accepted.
    Invalid evidence gets at most three attempts; model failures fall back
    immediately so the source facts remain available.
    """

    def __init__(self, settings: Settings) -> None:
        self.enabled = bool(settings.openrouter_api_key)
        self.agent = (
            Agent(
                _model(settings),
                output_type=ReputationAggregateOutput,
                instructions=REPUTATION_AGGREGATOR_INSTRUCTIONS,
                model_settings={"temperature": 0},
            )
            if self.enabled
            else None
        )

    async def aggregate(self, view: ReputationView) -> list[Observation]:
        if not view.chapters:
            return []

        if not self.agent:
            logger.info("ReputationAgent: model disabled; using source factors")
            return self._source_observations(view)

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
        allowed_by_chapter = {
            chapter: {entry.field("name") for entry in entries}
            for chapter, entries in view.by_chapter.items()
        }
        values = {entry.field("name"): entry.item.name for entry in view.indexed}
        base_prompt = json.dumps(payload, ensure_ascii=False)
        for attempt in range(1, 4):
            prompt = base_prompt
            if attempt > 1:
                prompt += (
                    "\n\nПредыдущий ответ содержит некорректные ссылки. "
                    "Верни непустой highlights и укажи для каждого утверждения "
                    "хотя бы одно точное поле field из его раздела chapter."
                )
            try:
                logger.info("LLM call -> ReputationAgent.aggregate attempt=%d", attempt)
                result = await self.agent.run(prompt)
            except Exception:
                logger.exception("Reputation model failed; using source factors")
                return self._source_observations(view)

            highlights = result.output.highlights
            if highlights and all(
                highlight.chapter in allowed_by_chapter
                and highlight.evidence_fields
                and set(highlight.evidence_fields).issubset(
                    allowed_by_chapter[highlight.chapter]
                )
                for highlight in highlights
            ):
                logger.info("LLM call <- ReputationAgent.aggregate attempt=%d", attempt)
                return [
                    Observation(
                        code=f"chapter_{highlight.chapter}",
                        title=highlight.title,
                        detail=highlight.text,
                        evidence=[
                            Evidence(field=field, value=values[field])
                            for field in dict.fromkeys(highlight.evidence_fields)
                        ],
                    )
                    for highlight in highlights
                ]
            logger.warning("Reputation evidence validation failed attempt=%d", attempt)

        logger.warning("Reputation evidence retries exhausted; using source factors")
        return self._source_observations(view)

    @staticmethod
    def _source_observations(view: ReputationView) -> list[Observation]:
        return [
            Observation(
                code=f"chapter_{chapter}",
                title=CHAPTER_LABELS.get(chapter, chapter),
                detail="; ".join(dict.fromkeys(entry.item.name for entry in entries)),
                evidence=[entry.evidence("name") for entry in entries],
            )
            for chapter, entries in view.by_chapter.items()
        ]



@lru_cache
def get_reputation_agent() -> ReputationAgent:
    """Lazily-cached singleton: the only way to hand `Settings` to the
    reputation MCP tool, which otherwise takes just a `CounterpartyCard`
    (same pattern as `settings.get_settings`).
    """
    return ReputationAgent(get_settings())
