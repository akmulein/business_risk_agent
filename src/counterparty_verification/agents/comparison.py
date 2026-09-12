from __future__ import annotations

import json
import logging
from time import perf_counter
from typing import Any

from pydantic_ai import Agent

from counterparty_verification.agents.prompts import COMPARISON_INSTRUCTIONS
from counterparty_verification.agents.provider import _model
from counterparty_verification.agents.summary_context import chapter_context
from counterparty_verification.domain import (
    ChapterResult,
    ComparisonCompany,
    RiskLevel,
    VerificationStatus,
)
from counterparty_verification.settings import Settings

logger = logging.getLogger(__name__)

RISK_LABELS = {
    RiskLevel.LOW: "низкий",
    RiskLevel.MEDIUM: "средний",
    RiskLevel.HIGH: "высокий",
    RiskLevel.UNKNOWN: "не определён",
}

STATUS_LABELS = {
    VerificationStatus.OK: "замечаний нет",
    VerificationStatus.ISSUE: "есть замечания",
    VerificationStatus.NO_DATA: "нет данных",
}


def _company_report(company: ComparisonCompany) -> dict[str, Any]:
    """Same figures, every status already spelled out in Russian.

    The model can only repeat what it is given, so raw enum values such as
    ``LOW`` or ``ISSUE`` must never reach it.
    """
    report = company.model_dump(mode="json", exclude={"rank"}, exclude_none=True)
    report["risk_level"] = RISK_LABELS[company.risk_level]
    report["fns_status"] = STATUS_LABELS[company.fns_status]
    report["bankruptcy_status"] = STATUS_LABELS[company.bankruptcy_status]
    return report


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
                    "report": _company_report(company),
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
