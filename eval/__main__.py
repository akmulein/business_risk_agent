from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from .common import DEFAULT_RESULTS, DEFAULT_SNAPSHOT


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("prepare", "run", "export-handoff"),
    )
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument("--destination", type=Path)
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.command == "prepare":
        from .protocol import prepare

        protocol = prepare(args.snapshot, args.results)
        print(
            json.dumps(
                {
                    "protocol": str(args.results / "protocol.json"),
                    "raw_snapshot_sha256": protocol["raw_snapshot_sha256"],
                    **protocol["expected"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    elif args.command == "run":
        from .runner import run_all

        asyncio.run(run_all(args.results))
    else:
        from .export import export_handoff

        destination = export_handoff(args.results, args.destination)
        print(destination)


if __name__ == "__main__":
    main()
