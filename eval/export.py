"""Сборка результатов тестирования для внешнего судьи"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .common import DEFAULT_RESULTS, load_json, raw_reports_by_inn, resolve_repository_path, save_json
from .protocol import load_frozen_protocol

TOOLS = (
    "analyze_general",
    "analyze_structure",
    "analyze_legal",
    "analyze_reputation",
    "analyze_finance",
    "analyze_procurement",
)


def _case_id(plan: dict[str, Any]) -> str:
    return f"{plan['group_id']}.{plan['run_id']}"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")


def _inn_from_raw(report: dict[str, Any]) -> str:
    return str(report.get("baseInfo", {}).get("inn", "")).strip()


def _company_name(report: dict[str, Any]) -> str | None:
    base = report.get("baseInfo", {})
    return base.get("shortName") or base.get("fullName") or base.get("name")


def _maybe_load(path: Path) -> Any:
    return load_json(path) if path.exists() else None


def _case_summary(case: Path) -> dict[str, Any]:
    response = load_json(case / "response.json")
    comparison = load_json(case / "comparison.json")
    return {
        "request": load_json(case / "request.json"),
        "response_metadata": {
            key: response.get(key)
            for key in ("http_status", "headers", "seconds", "completed_at")
        },
        "individual_summaries": load_json(case / "individual-summaries.json"),
        "comparative_summary": comparison.get("summary"),
        "comparison_error": comparison.get("summary_error"),
        "structured_comparison": load_json(case / "structured-comparison.json"),
        "comparison_model_input": load_json(case / "model-inputs/comparison/comparison.json"),
        "comparison_model_call": _maybe_load(case / "model-calls/comparison/comparison.json"),
        "errors": load_json(case / "errors.json"),
    }


def _validate_generated(results: Path, protocol: dict[str, Any], raw_by_inn: dict[str, dict[str, Any]]) -> None:
    problems: list[str] = []
    groups = protocol["main_groups"]
    sizes = Counter(len(value) for value in groups.values())
    inns = [inn for group in groups.values() for inn in group]
    if len(groups) != 30:
        problems.append(f"main groups: {len(groups)}")
    if sizes != Counter({2: 10, 3: 10, 5: 10}):
        problems.append(f"group sizes: {dict(sizes)}")
    if len(set(inns)) != 100:
        problems.append(f"unique INNs: {len(set(inns))}")
    if set(inns) != set(raw_by_inn):
        problems.append("raw snapshot does not match protocol INNs")
    for plan in protocol["generation_plan"]:
        case = results / "cases" / _case_id(plan)
        for rel in (
            "request.json",
            "response.json",
            "individual-summaries.json",
            "comparison.json",
            "structured-comparison.json",
            "errors.json",
            "model-inputs/comparison/comparison.json",
        ):
            if not (case / rel).exists():
                problems.append(f"{_case_id(plan)}: missing {rel}")
        if (case / "comparison.json").exists() and not load_json(case / "comparison.json").get("summary"):
            problems.append(f"{_case_id(plan)}: missing comparative summary")
        summaries = (
            {str(item.get("inn")): item for item in load_json(case / "individual-summaries.json")}
            if (case / "individual-summaries.json").exists()
            else {}
        )
        for inn in plan["inns"]:
            if not summaries.get(inn, {}).get("summary"):
                problems.append(f"{_case_id(plan)}: missing individual summary for {inn}")
            if not (case / "model-inputs/individual" / f"{inn}.json").exists():
                problems.append(f"{_case_id(plan)}: missing individual model input for {inn}")
            if plan["evaluation_set"] == "main":
                for tool in TOOLS:
                    if not (case / "tools" / inn / f"{tool}.json").exists():
                        problems.append(f"{_case_id(plan)}: missing {tool} output for {inn}")
    if problems:
        raise RuntimeError("Generated benchmark is incomplete:\n" + "\n".join(problems[:100]))


def export_handoff(results: Path = DEFAULT_RESULTS, destination: Path | None = None) -> Path:
    """Export compact generated artifacts for external factual review.

    The export contains raw reports once in ``companies.jsonl``. Stability rows do
    not duplicate raw reports or deterministic tool outputs; they reference the
    main company records.
    """
    protocol = load_frozen_protocol(results)
    snapshot = resolve_repository_path(protocol["raw_snapshot"])
    raw_by_inn = raw_reports_by_inn(snapshot)
    _validate_generated(results, protocol, raw_by_inn)
    destination = destination or (results / "handoff")
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)

    main_plans = [item for item in protocol["generation_plan"] if item["evaluation_set"] == "main"]
    stability_plans = [item for item in protocol["generation_plan"] if item["evaluation_set"] == "stability"]
    company_rows: list[dict[str, Any]] = []
    for plan in main_plans:
        case = results / "cases" / _case_id(plan)
        summaries = {str(item.get("inn")): item for item in load_json(case / "individual-summaries.json")}
        for inn in plan["inns"]:
            report = raw_by_inn[inn]
            company_rows.append(
                {
                    "inn": inn,
                    "company_name": _company_name(report),
                    "main_group_id": plan["group_id"],
                    "main_case_id": _case_id(plan),
                    "raw_report": report,
                    "production_tool_outputs": {
                        tool: load_json(case / "tools" / inn / f"{tool}.json")
                        for tool in TOOLS
                    },
                    "individual_model_input": load_json(case / "model-inputs/individual" / f"{inn}.json"),
                    "individual_model_call": _maybe_load(case / "model-calls/individual" / f"{inn}.json"),
                    "individual_summary": summaries[inn],
                }
            )
    _write_jsonl(destination / "companies.jsonl", company_rows)
    comparison_rows = [
        {
            "evaluation_set": "main",
            "group_id": plan["group_id"],
            "run_id": plan["run_id"],
            "case_id": _case_id(plan),
            "inns": plan["inns"],
            **_case_summary(results / "cases" / _case_id(plan)),
        }
        for plan in main_plans
    ]
    _write_jsonl(destination / "comparisons.jsonl", comparison_rows)
    stability_rows = [
        {
            "evaluation_set": "stability",
            "group_id": plan["group_id"],
            "run_id": plan["run_id"],
            "case_id": _case_id(plan),
            "inns": plan["inns"],
            "raw_reports_included": False,
            "production_tool_outputs_included": False,
            "uses_main_company_records_for_raw_and_tools": True,
            **_case_summary(results / "cases" / _case_id(plan)),
        }
        for plan in stability_plans
    ]
    _write_jsonl(destination / "stability.jsonl", stability_rows)
    files = [
        {"path": path.name, "bytes": path.stat().st_size, "sha256": _sha256_file(path)}
        for path in sorted(destination.iterdir())
        if path.is_file()
    ]
    save_json(
        destination / "manifest.json",
        {
            "version": "benchmark-compact-handoff",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source_results": str(results),
            "benchmark": {
                "protocol_version": protocol["version"],
                "protocol_frozen_at": protocol.get("frozen_at"),
                "raw_snapshot": protocol["raw_snapshot"],
                "raw_snapshot_sha256": protocol["raw_snapshot_sha256"],
                "runtime_config": protocol.get("runtime_config"),
                "production": protocol.get("production"),
                "benchmark_code": protocol.get("benchmark"),
            },
            "scope": {
                "main_cases": 30,
                "main_companies": 100,
                "main_individual_summaries": 100,
                "main_comparative_summaries": 30,
                "stability_additional_runs": 12,
                "stability_groups": protocol.get("stability_groups"),
                "comparison_group_sizes": {"2_companies": 10, "3_companies": 10, "5_companies": 10},
                "contains_judge_verdicts": False,
                "contains_quality_labels": False,
                "contains_summary_correctness_assessment": False,
            },
            "files": files,
        },
    )
    return destination
