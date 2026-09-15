"""Служебные функции"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SNAPSHOT = ROOT / "mongo_db/contractors_audit.snapshot.json"
DEFAULT_RESULTS = ROOT / "eval/results/run"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_json(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def raw_reports_by_inn(snapshot_path: Path) -> dict[str, dict[str, Any]]:
    roots = load_json(snapshot_path)
    if not isinstance(roots, list):
        raise ValueError("Raw snapshot must be a JSON array")
    result: dict[str, dict[str, Any]] = {}
    for index, root in enumerate(roots):
        if not isinstance(root, dict) or not isinstance(root.get("report"), dict):
            raise ValueError(f"Snapshot item {index} has no report object")
        report = root["report"]
        inn = str(report.get("baseInfo", {}).get("inn", "")).strip()
        if not inn:
            raise ValueError(f"Snapshot item {index} has no report.baseInfo.inn")
        if inn in result:
            raise ValueError(f"Duplicate INN in raw snapshot: {inn}")
        result[inn] = report
    return result


def repository_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(ROOT))
    except ValueError:
        return str(resolved)


def resolve_repository_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def git_commit() -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() or None


def file_hashes(paths: list[Path]) -> dict[str, str]:
    return {
        repository_path(path): sha256_file(path)
        for path in sorted(paths)
        if path.is_file()
    }


def production_hashes() -> dict[str, str]:
    paths = list((ROOT / "app").rglob("*.py"))
    paths.extend(
        path
        for path in (
            ROOT / "pyproject.toml",
            ROOT / "Dockerfile",
            ROOT / "docker-compose.yml",
            ROOT / "mongo_db/build_read_model.js",
        )
        if path.exists()
    )
    return file_hashes(paths)


def benchmark_hashes() -> dict[str, str]:
    return file_hashes(list((ROOT / "eval").glob("*.py")))
