from __future__ import annotations

import hashlib
import json
import logging
from time import perf_counter

from pydantic_ai import Agent

from counterparty_verification.agents.prompts import EVALUATOR_INSTRUCTIONS
from counterparty_verification.agents.provider import _model
from counterparty_verification.agents.summary_context import (
    GroundedSummary,
    chapter_context,
    validate_selected_facts,
)
from counterparty_verification.analysis.timing import record, record_llm_result, timed
from counterparty_verification.domain import (
    AnalysisSummary,
    ChapterResult,
    ComparisonCompany,
    RiskLevel,
)
from counterparty_verification.settings import Settings

logger = logging.getLogger(__name__)


class EvaluatorAgent:
    def __init__(self, settings: Settings) -> None:
        self.enabled = bool(settings.openrouter_api_key)
        self.agent = (
            Agent(
                _model(settings),
                output_type=GroundedSummary,
                instructions=EVALUATOR_INSTRUCTIONS,
                # OpenRouter load-balances across providers serving the same
                # model; sorting by throughput avoids providers whose token
                # generation is much slower than the rest for the same output.
                # Reasoning tokens aren't part of the summary we show, and
                # measured runs showed them costing as many (or more) tokens
                # than the actual answer -- disable them.
                model_settings={
                    "temperature": 0,
                    "openrouter_provider": {"sort": "throughput"},
                    "openrouter_reasoning": {"enabled": False},
                },
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
        company: ComparisonCompany,
    ) -> AnalysisSummary:
        if not self.agent:
            raise RuntimeError("OPENROUTER_API_KEY is not configured")

        facts = chapter_context(chapters, "A", company)
        payload = {
            "companies": [
                {
                    "company_id": "A",
                    "company_name": company_name,
                    "facts": facts,
                }
            ],
        }
        started = perf_counter()
        logger.info(
            "LLM call -> EvaluatorAgent.summarize company=%s chapters=%d",
            company_name,
            len(chapters),
        )
        prompt = json.dumps(payload, ensure_ascii=False)
        record(
            "llm_input",
            kind="individual",
            company=company_name,
            input_chars=len(prompt),
            input_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
        )
        with timed("llm", kind="individual", company=company_name):
            result = await self.agent.run(prompt)
        record_llm_result(result, kind="individual", company=company_name)
        validate_selected_facts(result.output, facts)
        summary = result.output.summary.strip()
        if not summary:
            raise RuntimeError("Evaluator returned an empty summary")
        logger.info(
            "LLM call <- EvaluatorAgent.summarize company=%s elapsed=%.3fs",
            company_name,
            perf_counter() - started,
        )
        return AnalysisSummary(risk_level=risk_level, summary=summary)
