from __future__ import annotations

import hashlib
import json
import logging
from time import perf_counter

from pydantic_ai import Agent

from counterparty_verification.agents.prompts import COMPARISON_INSTRUCTIONS
from counterparty_verification.agents.provider import _model
from counterparty_verification.agents.summary_context import (
    GroundedSummary,
    chapter_context,
    validate_selected_facts,
)
from counterparty_verification.analysis.timing import record, record_llm_result, timed
from counterparty_verification.domain import (
    ChapterResult,
    ComparisonCompany,
)
from counterparty_verification.settings import Settings

logger = logging.getLogger(__name__)

class ComparisonAgent:
    def __init__(self, settings: Settings) -> None:
        self.enabled = bool(settings.openrouter_api_key)
        self.agent = (
            Agent(
                _model(settings),
                output_type=GroundedSummary,
                instructions=COMPARISON_INSTRUCTIONS,
                # See agents/evaluator.py -- same reasoning for sorting
                # OpenRouter providers by throughput and disabling reasoning.
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
        companies: list[ComparisonCompany],
        chapters_by_inn: dict[str, list[ChapterResult]],
    ) -> str:
        if not self.agent:
            raise RuntimeError("OPENROUTER_API_KEY is not configured")

        payload_companies = []
        all_facts = []
        company_ids = set()
        for index, company in enumerate(companies):
            company_id = chr(ord("A") + index)
            company_ids.add(company_id)
            facts = chapter_context(
                chapters_by_inn[company.inn], company_id, company
            )
            all_facts.extend(facts)
            payload_companies.append(
                {
                    "company_id": company_id,
                    "company_name": company.name,
                    "facts": facts,
                }
            )
        payload = {"companies": payload_companies}
        inns = ",".join(company.inn for company in companies)
        started = perf_counter()
        logger.info("LLM call -> ComparisonAgent.summarize inns=%s", inns)
        prompt = json.dumps(payload, ensure_ascii=False)
        record(
            "llm_input",
            kind="comparison",
            inns=inns,
            input_chars=len(prompt),
            input_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
        )
        with timed("llm", kind="comparison", inns=inns):
            result = await self.agent.run(prompt)
        record_llm_result(result, kind="comparison", inns=inns)
        validate_selected_facts(
            result.output,
            all_facts,
            expected_company_ids=company_ids,
        )
        summary = result.output.summary.strip()
        if not summary:
            raise RuntimeError("Comparison model returned an empty summary")
        logger.info(
            "LLM call <- ComparisonAgent.summarize inns=%s elapsed=%.3fs",
            inns,
            perf_counter() - started,
        )
        return summary
