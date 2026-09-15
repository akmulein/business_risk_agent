from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from time import perf_counter
from typing import Any

import httpx

from app.api import create_app
from app.domain import CounterpartyCard
from app.mcp.client import LocalAnalysisToolClient
from app.settings import Settings
from app.storage.mongo import MongoCounterpartyRepository

from .capture import CapturingAgent, ResumableComparison, ResumableEvaluator
from .common import DEFAULT_RESULTS, load_json, raw_reports_by_inn, resolve_repository_path, save_json, utc_now
from .projection import validate_card_projection
from .protocol import load_frozen_protocol


class SnapshotRepository:
    def __init__(self, cards: list[CounterpartyCard], raw: dict[str, dict[str, Any]]) -> None:
        self.cards = {card.company_reports.inn: card for card in cards}
        self.raw = raw

    async def get_by_inn(self, inn: str) -> CounterpartyCard | None:
        return self.cards.get(inn)

    async def get_many_by_inns(self, inns: list[str]) -> list[CounterpartyCard]:
        return [self.cards[inn] for inn in inns if inn in self.cards]

    async def get_source_report_by_inn(self, inn: str) -> dict[str, Any] | None:
        return self.raw.get(inn)


class SavingTools(LocalAnalysisToolClient):
    def __init__(self, case: Path) -> None:
        self.case = case

    async def call(self, tool_name: str, card: CounterpartyCard) -> Any:
        result = await super().call(tool_name, card)
        path = self.case / "tools" / card.company_reports.inn / f"{tool_name}.json"
        value = result.model_dump(mode="json")
        if path.exists() and load_json(path) != value:
            raise RuntimeError(f"Deterministic tool output changed during resume: {path}")
        save_json(path, value)
        return result


def _runtime_matches(protocol: dict[str, Any], settings: Settings) -> None:
    actual = {
        "model_slug": settings.openrouter_model,
        "batch_chapter_concurrency": settings.batch_chapter_concurrency,
        "batch_llm_concurrency": settings.batch_llm_concurrency,
    }
    if actual != protocol["runtime_config"]:
        raise RuntimeError(
            f"Runtime config differs from frozen protocol: expected "
            f"{protocol['runtime_config']}, got {actual}"
        )


async def _load_cards(settings: Settings, inns: list[str], reports: dict[str, dict[str, Any]]) -> list[CounterpartyCard]:
    repository = MongoCounterpartyRepository(
        settings.mongodb_url,
        settings.mongodb_database,
        settings.mongodb_collection,
        source_collection=settings.mongodb_source_collection,
    )
    try:
        cards = await repository.get_many_by_inns(inns)
    finally:
        await repository.close()
    found = {card.company_reports.inn for card in cards}
    if found != set(inns):
        raise RuntimeError(f"Mongo read model mismatch; missing={sorted(set(inns)-found)}")
    failed = []
    for card in cards:
        checks = validate_card_projection(
            card.company_reports.inn,
            reports[card.company_reports.inn],
            card.model_dump(mode="json"),
        )
        failed.extend(item for item in checks if item["status"] == "fail")
    if failed:
        first = failed[0]
        raise RuntimeError(
            "Mongo read model does not match frozen raw snapshot: "
            f"{first['inn']} {first['field']}"
        )
    return cards


def _write_case_views(case: Path, body: dict[str, Any]) -> None:
    individual = []
    errors = []
    for item in body.get("results", []):
        analysis = item.get("analysis")
        if analysis:
            individual.append({"inn": item["inn"], "summary": analysis.get("summary")})
        if item.get("status") != "success" or item.get("error"):
            errors.append({"inn": item.get("inn"), "status": item.get("status"), "error": item.get("error")})
    comparison = body.get("comparison") or {}
    save_json(case / "individual-summaries.json", individual)
    save_json(
        case / "comparison.json",
        {"summary": comparison.get("summary"), "summary_error": comparison.get("summary_error")},
    )
    save_json(case / "structured-comparison.json", comparison.get("companies", []))
    call_errors = []
    for path in case.glob("model-calls/**/*.json"):
        call = load_json(path)
        if call.get("error"):
            call_errors.append({"path": str(path.relative_to(case)), "error": call["error"]})
    save_json(case / "errors.json", {"api_items": errors, "model_calls": call_errors})


async def _run_case(
    results: Path,
    protocol: dict[str, Any],
    settings: Settings,
    cards_by_inn: dict[str, CounterpartyCard],
    reports: dict[str, dict[str, Any]],
    plan: dict[str, Any],
) -> None:
    case_id = f"{plan['group_id']}.{plan['run_id']}"
    case = results / "cases" / case_id
    response_path = case / "response.json"
    if response_path.exists():
        print(f"skip {case_id}: response already saved", flush=True)
        return
    inns = plan["inns"]
    request = {"inns": inns}
    metadata = {
        **plan,
        "case_id": case_id,
        "configured_model": settings.openrouter_model,
        "started_at": utc_now(),
    }
    request_path = case / "request.json"
    request_record = {"metadata": metadata, "request": request}
    if request_path.exists():
        saved_request = load_json(request_path)
        stable_metadata = {
            key: metadata[key]
            for key in (
                "group_id",
                "run_id",
                "inns",
                "evaluation_set",
                "case_id",
                "configured_model",
            )
        }
        saved_stable_metadata = {
            key: saved_request.get("metadata", {}).get(key)
            for key in stable_metadata
        }
        if saved_request.get("request") != request or saved_stable_metadata != stable_metadata:
            raise RuntimeError(f"Request changed during resume: {request_path}")
    else:
        save_json(request_path, request_record)
    cards = [cards_by_inn[inn] for inn in inns]
    repository = SnapshotRepository(cards, {inn: reports[inn] for inn in inns})
    app = create_app(settings, repository=repository)
    service = app.state.analysis_service
    service.tools = SavingTools(case)
    names = {
        card.company_reports.short_name or card.company_reports.full_name or card.company_reports.inn: card.company_reports.inn
        for card in cards
    }
    if len(names) != len(cards):
        raise RuntimeError(f"Company names are ambiguous in {case_id}")
    service.evaluator.agent = CapturingAgent(
        service.evaluator.agent, case, "individual", names, settings.openrouter_model
    )
    service.comparison_agent.agent = CapturingAgent(
        service.comparison_agent.agent, case, "comparison", names, settings.openrouter_model
    )
    service.evaluator = ResumableEvaluator(service.evaluator, case)
    service.comparison_agent = ResumableComparison(service.comparison_agent, case)
    started = perf_counter()
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://benchmark.local",
            timeout=None,
        ) as client:
            response = await client.post("/api/v1/analyses", json=request)
    record = {
        "http_status": response.status_code,
        "headers": {key: value for key, value in response.headers.items() if key.lower().startswith("x-")},
        "body": response.json(),
        "seconds": perf_counter() - started,
        "completed_at": utc_now(),
    }
    save_json(response_path, record)
    _write_case_views(case, record["body"])
    print(f"complete {case_id}: HTTP {response.status_code}, {record['seconds']:.1f}s", flush=True)


async def run_all(results: Path = DEFAULT_RESULTS) -> None:
    logging.getLogger().setLevel(logging.ERROR)
    protocol = load_frozen_protocol(results)
    settings = Settings()
    _runtime_matches(protocol, settings)
    if not settings.openrouter_api_key:
        raise RuntimeError("OPENROUTER_API_KEY is required for generation")
    snapshot = resolve_repository_path(protocol["raw_snapshot"])
    reports = raw_reports_by_inn(snapshot)
    all_inns = [inn for group in protocol["main_groups"].values() for inn in group]
    cards = await _load_cards(settings, all_inns, reports)
    cards_by_inn = {card.company_reports.inn: card for card in cards}
    for plan in protocol["generation_plan"]:
        await _run_case(results, protocol, settings, cards_by_inn, reports, plan)
