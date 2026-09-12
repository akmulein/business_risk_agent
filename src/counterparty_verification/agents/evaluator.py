from __future__ import annotations

import json
import logging
from time import perf_counter

from pydantic_ai import Agent

from counterparty_verification.agents.prompts import EVALUATOR_INSTRUCTIONS
from counterparty_verification.agents.provider import _model
from counterparty_verification.agents.summary_context import chapter_context
from counterparty_verification.domain import AnalysisSummary, ChapterResult, RiskLevel
from counterparty_verification.settings import Settings

logger = logging.getLogger(__name__)


class EvaluatorAgent:
    def __init__(self, settings: Settings) -> None:
        self.enabled = bool(settings.openrouter_api_key)
        self.agent = (
            Agent(
                _model(settings),
                output_type=str,
                instructions=EVALUATOR_INSTRUCTIONS,
                model_settings={"temperature": 0},
                retries=0,
            )
            if self.enabled
            else None
        )

    async def summarize(
        self,
        company_name: str,
        risk_level: RiskLevel,
        chapters: list[ChapterResult],
    ) -> AnalysisSummary:
        if not self.agent:
            raise RuntimeError("OPENROUTER_API_KEY is not configured")

        payload = {
            "company": company_name,
            "bank_risk_level": risk_level.value,
            "chapters": chapter_context(chapters),
        }
        started = perf_counter()
        logger.info(
            "LLM call -> EvaluatorAgent.summarize company=%s chapters=%d",
            company_name,
            len(chapters),
        )
        result = await self.agent.run(json.dumps(payload, ensure_ascii=False))
        summary = result.output.strip()
        if not summary:
            raise RuntimeError("Evaluator returned an empty summary")
        logger.info(
            "LLM call <- EvaluatorAgent.summarize company=%s elapsed=%.3fs",
            company_name,
            perf_counter() - started,
        )
        return AnalysisSummary(risk_level=risk_level, summary=summary)
