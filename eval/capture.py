"""Cохранение LLM-вызовов"""

from __future__ import annotations

import json
from pathlib import Path
from time import perf_counter
from typing import Any

from app.agents.summary_context import (
    GroundedSummary,
    chapter_context,
    validate_selected_facts,
)
from app.domain import AnalysisSummary

from .common import load_json, save_json, utc_now


class UncertainProviderOutcome(RuntimeError):
    pass


def _usage_value(usage: Any, name: str) -> Any:
    value = getattr(usage, name, None)
    return value() if callable(value) else value


class CapturingAgent:
    def __init__(
        self,
        agent: Any,
        case: Path,
        kind: str,
        name_to_inn: dict[str, str],
        configured_model: str,
    ) -> None:
        self.agent = agent
        self.case = case
        self.kind = kind
        self.name_to_inn = name_to_inn
        self.configured_model = configured_model

    def _key(self, payload: dict[str, Any]) -> str:
        if self.kind == "comparison":
            return "comparison"
        companies = payload.get("companies", [])
        if len(companies) != 1:
            raise RuntimeError("Individual model input must contain one company")
        name = companies[0].get("company_name")
        if name not in self.name_to_inn:
            raise RuntimeError(f"Cannot map model input to INN: {name!r}")
        return self.name_to_inn[name]

    async def run(self, prompt: str, *args: Any, **kwargs: Any) -> Any:
        payload = json.loads(prompt)
        key = self._key(payload)
        input_path = self.case / "model-inputs" / self.kind / f"{key}.json"
        call_path = self.case / "model-calls" / self.kind / f"{key}.json"
        if call_path.exists():
            raise RuntimeError(f"Unexpected duplicate provider call: {call_path}")
        save_json(input_path, payload)
        call = {
            "state": "in_flight",
            "kind": self.kind,
            "key": key,
            "configured_model": self.configured_model,
            "started_at": utc_now(),
            "input": payload,
        }
        save_json(call_path, call)
        started = perf_counter()
        try:
            result = await self.agent.run(prompt, *args, **kwargs)
            response = result.response
            usage = result.usage
            provider_details = response.provider_details or {}
            output = result.output
            call.update(
                {
                    "state": "complete",
                    "completed_at": utc_now(),
                    "seconds": perf_counter() - started,
                    "actual_model": response.model_name,
                    "provider": response.provider_name,
                    "downstream_provider": provider_details.get("downstream_provider"),
                    "generation_id": response.provider_response_id,
                    "finish_reason": response.finish_reason,
                    "usage": {
                        "requests": _usage_value(usage, "requests"),
                        "input_tokens": _usage_value(usage, "input_tokens"),
                        "output_tokens": _usage_value(usage, "output_tokens"),
                        "cached_input_tokens": _usage_value(usage, "cache_read_tokens"),
                        "details": getattr(usage, "details", None),
                    },
                    "cost_usd": provider_details.get("cost"),
                    "provider_details": provider_details,
                    "raw_output": (
                        output.model_dump(mode="json")
                        if hasattr(output, "model_dump")
                        else output
                    ),
                }
            )
            return result
        except BaseException as error:
            call.update(
                {
                    "state": "complete",
                    "completed_at": utc_now(),
                    "seconds": perf_counter() - started,
                    "error": {
                        "type": type(error).__name__,
                        "message": str(error),
                    },
                }
            )
            raise
        finally:
            save_json(call_path, call)


def _saved_output(call_path: Path, expected_input: dict[str, Any]) -> GroundedSummary | None:
    if not call_path.exists():
        return None
    call = load_json(call_path)
    if call.get("state") == "in_flight":
        raise UncertainProviderOutcome(
            f"Provider outcome is uncertain: {call_path}. Inspect it before retrying."
        )
    if call.get("input") != expected_input:
        raise RuntimeError(f"Saved model input does not match current input: {call_path}")
    if call.get("error"):
        raise RuntimeError(f"Saved provider call failed: {call_path}")
    return GroundedSummary.model_validate(call.get("raw_output"))


class ResumableEvaluator:
    def __init__(self, owner: Any, case: Path) -> None:
        self.owner = owner
        self.case = case

    async def summarize(self, company_name: str, risk_level: Any, chapters: Any, company: Any) -> AnalysisSummary:
        facts = chapter_context(chapters, "A", company)
        payload = {
            "companies": [
                {"company_id": "A", "company_name": company_name, "facts": facts}
            ]
        }
        call_path = self.case / "model-calls/individual" / f"{company.inn}.json"
        saved = _saved_output(call_path, payload)
        if saved is None:
            return await self.owner.summarize(company_name, risk_level, chapters, company)
        validate_selected_facts(saved, facts)
        return AnalysisSummary(risk_level=risk_level, summary=saved.summary.strip())


class ResumableComparison:
    def __init__(self, owner: Any, case: Path) -> None:
        self.owner = owner
        self.case = case

    async def summarize(self, companies: list[Any], chapters_by_inn: dict[str, Any]) -> str:
        payload_companies = []
        all_facts = []
        company_ids = set()
        for index, company in enumerate(companies):
            company_id = chr(ord("A") + index)
            company_ids.add(company_id)
            facts = chapter_context(chapters_by_inn[company.inn], company_id, company)
            all_facts.extend(facts)
            payload_companies.append(
                {"company_id": company_id, "company_name": company.name, "facts": facts}
            )
        payload = {"companies": payload_companies}
        call_path = self.case / "model-calls/comparison/comparison.json"
        saved = _saved_output(call_path, payload)
        if saved is None:
            return await self.owner.summarize(companies, chapters_by_inn)
        validate_selected_facts(saved, all_facts, expected_company_ids=company_ids)
        return saved.summary.strip()
