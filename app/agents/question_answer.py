from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from app.agents.prompts import (
    QUESTION_ANSWER_INSTRUCTIONS,
)
from app.agents.provider import _model
from app.domain import (
    ChapterResult,
    CounterpartyCard,
)
from app.settings import Settings

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
            logger.info("LLM call skipped (QuestionAnswerAgent.answer): agent disabled")
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
