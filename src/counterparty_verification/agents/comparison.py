from __future__ import annotations

import json
import logging
from time import perf_counter

from pydantic_ai import Agent

from counterparty_verification.agents.prompts import COMPARISON_INSTRUCTIONS
from counterparty_verification.agents.provider import _model
from counterparty_verification.agents.summary_context import chapter_context
from counterparty_verification.domain import ChapterResult, ComparisonCompany
from counterparty_verification.settings import Settings

logger = logging.getLogger(__name__)


class ComparisonAgent:
    def __init__(self, settings: Settings) -> None:
        self.enabled = bool(settings.openrouter_api_key)
        self.agent = (
            Agent(
                _model(settings),
                output_type=str,
                instructions=COMPARISON_INSTRUCTIONS,
                model_settings={"temperature": 0},
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

        payload = {
            "companies": [
                {
                    "report": company.model_dump(
                        mode="json", exclude={"rank"}, exclude_none=True
                    ),
                    "chapters": chapter_context(chapters_by_inn[company.inn]),
                }
                for company in companies
            ],
        }
        inns = ",".join(company.inn for company in companies)
        started = perf_counter()
        logger.info("LLM call -> ComparisonAgent.summarize inns=%s", inns)
        result = await self.agent.run(json.dumps(payload, ensure_ascii=False))
        summary = result.output.strip()
        if not summary:
            raise RuntimeError("Comparison model returned an empty summary")
        logger.info(
            "LLM call <- ComparisonAgent.summarize inns=%s elapsed=%.3fs",
            inns,
            perf_counter() - started,
        )
        return summary
