"""Frozen groups and protocol creation for the evaluation benchmark."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from app.settings import Settings

from .common import (
    DEFAULT_RESULTS,
    benchmark_hashes,
    git_commit,
    load_json,
    production_hashes,
    raw_reports_by_inn,
    repository_path,
    resolve_repository_path,
    save_json,
    sha256_file,
    sha256_json,
    utc_now,
)


MAIN_GROUPS: dict[str, list[str]] = {
    "G01": ["5029069967", "9706026247"],
    "G02": ["052500690823", "343703064945", "9714021411"],
    "G03": ["2016003057", "234701002417", "772601396114", "6321305439", "2100006761"],
    "G04": ["1660266560", "3715005612"],
    "G05": ["9714079997", "7802932240", "3666269345"],
    "G06": ["421412008124", "2364004929", "501207152100", "3664234989", "7708332207"],
    "G07": ["592061218009", "0278949271"],
    "G08": ["7805327192", "3123346195", "620417452834"],
    "G09": ["5032257375", "2368001703", "301110278577", "5074059470", "6311087260"],
    "G10": ["2311304742", "7816085851"],
    "G11": ["8622002583", "6164137887", "505305266801"],
    "G12": ["7708336868", "2312263270", "773467509356", "9721079780", "2466275727"],
    "G13": ["9727128465", "7813664770"],
    "G14": ["7728380537", "7826131151", "616205958623"],
    "G15": ["3711039473", "4720028039", "5261137785", "7103029029", "6732241319"],
    "G16": ["010701412150", "9713021306"],
    "G17": ["9724033310", "9721159668", "7449088645"],
    "G18": ["7720966601", "9701318454", "6452924721", "1327036448", "7714497158"],
    "G19": ["9701166515", "770804624926"],
    "G20": ["7810984404", "233000064283", "9714038662"],
    "G21": ["1901132406", "234803704704", "7714729497", "7104080194", "9727071240"],
    "G22": ["7720901442", "771965001547"],
    "G23": ["666201003180", "2901324364", "5001146298"],
    "G24": ["6165169320", "772377037026", "9703030189", "7751352552", "5837083280"],
    "G25": ["780216530635", "615513451530"],
    "G26": ["7724398540", "540325003268", "0278917431"],
    "G27": ["9703198304", "4000036100", "6731007348", "8905068592", "1684017097"],
    "G28": ["7447131126", "120705254031"],
    "G29": ["9201513489", "470606601830", "9705152496"],
    "G30": ["5036158015", "503200230096", "3100037306", "5244026965", "1650051822"],
}
STABILITY_GROUPS = ("G01", "G02", "G09", "G20", "G25", "G27")
PROTOCOL_VERSION = "benchmark"


def assert_group_invariants(snapshot_inns: set[str]) -> None:
    if len(MAIN_GROUPS) != 30:
        raise AssertionError("Expected exactly 30 main groups")
    sizes = Counter(map(len, MAIN_GROUPS.values()))
    if sizes != Counter({2: 10, 3: 10, 5: 10}):
        raise AssertionError(f"Unexpected group-size distribution: {dict(sizes)}")
    flattened = [inn for group in MAIN_GROUPS.values() for inn in group]
    counts = Counter(flattened)
    duplicates = sorted(inn for inn, count in counts.items() if count != 1)
    if duplicates:
        raise AssertionError(f"INNs repeated across groups: {duplicates}")
    grouped = set(flattened)
    if len(grouped) != 100:
        raise AssertionError(f"Expected 100 unique grouped INNs, got {len(grouped)}")
    missing = sorted(grouped - snapshot_inns)
    extra = sorted(snapshot_inns - grouped)
    if missing or extra:
        raise AssertionError(
            f"Group/snapshot mismatch; missing={missing}, extra={extra}"
        )
    if not set(STABILITY_GROUPS).issubset(MAIN_GROUPS):
        raise AssertionError("Unknown stability group")


def build_protocol(snapshot: Path) -> dict[str, Any]:
    reports = raw_reports_by_inn(snapshot)
    assert_group_invariants(set(reports))
    settings = Settings()
    prod = production_hashes()
    bench = benchmark_hashes()
    prompt_paths = [
        "app/agents/prompts.py",
        "app/agents/summary_context.py",
        "app/agents/evaluator.py",
        "app/agents/comparison.py",
    ]
    return {
        "version": PROTOCOL_VERSION,
        "frozen_at": utc_now(),
        "raw_snapshot": repository_path(snapshot),
        "raw_snapshot_sha256": sha256_file(snapshot),
        "main_groups": MAIN_GROUPS,
        "stability_groups": list(STABILITY_GROUPS),
        "expected": {
            "main_groups": 30,
            "main_individual_n": 100,
            "main_comparison_n": 30,
            "comparison_group_sizes": {"2": 10, "3": 10, "5": 10},
            "stability_groups": 6,
            "stability_additional_runs": 12,
        },
        "generation_plan": [
            {
                "group_id": group_id,
                "run_id": run_id,
                "inns": inns,
                "evaluation_set": "main" if run_id == "r1" else "stability",
            }
            for group_id, inns in MAIN_GROUPS.items()
            for run_id in (
                ("r1", "r2", "r3")
                if group_id in STABILITY_GROUPS
                else ("r1",)
            )
        ],
        "production": {
            "git_commit": git_commit(),
            "code_sha256": sha256_json(prod),
            "file_hashes": prod,
            "prompt_hashes": {
                path: prod[path] for path in prompt_paths if path in prod
            },
        },
        "benchmark": {
            "code_sha256": sha256_json(bench),
            "file_hashes": bench,
        },
        "runtime_config": {
            "model_slug": settings.openrouter_model,
            "batch_chapter_concurrency": settings.batch_chapter_concurrency,
            "batch_llm_concurrency": settings.batch_llm_concurrency,
        },
        "methodology": {
            "source_of_truth": "raw report",
            "judge": "external blind LLM reviewer; not run by this benchmark",
            "quality_denominators": {
                "individual": 100,
                "comparison": 30,
            },
            "stability_excluded_from_quality_metrics": True,
        },
    }


def prepare(snapshot: Path, results: Path = DEFAULT_RESULTS) -> dict[str, Any]:
    protocol_path = results / "protocol.json"
    if protocol_path.exists():
        raise FileExistsError(
            f"Frozen protocol already exists: {protocol_path}. "
            "Delete it explicitly to start a different benchmark."
        )
    protocol = build_protocol(snapshot.resolve())
    save_json(protocol_path, protocol)
    return protocol


def load_frozen_protocol(results: Path = DEFAULT_RESULTS) -> dict[str, Any]:
    path = results / "protocol.json"
    if not path.exists():
        raise FileNotFoundError(f"Run prepare first: {path}")
    protocol = load_json(path)
    if protocol.get("version") != PROTOCOL_VERSION:
        raise ValueError(f"Unsupported protocol version: {protocol.get('version')}")
    snapshot = resolve_repository_path(protocol["raw_snapshot"])
    if sha256_file(snapshot) != protocol["raw_snapshot_sha256"]:
        raise RuntimeError("Frozen raw snapshot has changed")
    assert_group_invariants(set(raw_reports_by_inn(snapshot)))
    current = production_hashes()
    if sha256_json(current) != protocol["production"]["code_sha256"]:
        changed = sorted(
            path
            for path in set(current) | set(protocol["production"]["file_hashes"])
            if current.get(path) != protocol["production"]["file_hashes"].get(path)
        )
        raise RuntimeError("Frozen production code changed: " + ", ".join(changed))
    current_benchmark = benchmark_hashes()
    if sha256_json(current_benchmark) != protocol["benchmark"]["code_sha256"]:
        raise RuntimeError("benchmark code changed after prepare")
    return protocol
