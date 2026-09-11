from __future__ import annotations

import json
import logging

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from counterparty_verification.agents.prompts import (
    EVALUATOR_INSTRUCTIONS,
)
from counterparty_verification.agents.provider import _model
from counterparty_verification.domain import (
    AnalysisSummary,
    FactorSummaryItem,
    RiskLevel,
)
from counterparty_verification.settings import Settings

logger = logging.getLogger(__name__)


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
                    raise RuntimeError("Summary contains unknown fact identifiers")
                used_ids = {
                    fact_id
                    for statement in result.output.statements
                    for fact_id in statement.fact_ids
                }
                logger.info("LLM call <- EvaluatorAgent.summarize attempt=%d", attempt)
                return AnalysisSummary(
                    risk_level=risk_level,
                    summary=" ".join(item.text for item in result.output.statements),
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
        raise RuntimeError("Summary generation failed after 3 attempts") from last_error
