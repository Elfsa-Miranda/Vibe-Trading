"""Shared runner and output helpers for Alpha Foundry demos."""

from __future__ import annotations

import argparse
import difflib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any


def canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"


def run_demo_cli(demo_dir: Path, build_output: Callable[[], dict[str, Any]]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--write-snapshot", action="store_true")
    args = parser.parse_args()

    current = build_output()
    snapshot_path = demo_dir / "expected_output.json"
    current_json = canonical_json(current)

    if args.write_snapshot:
        snapshot_path.write_text(current_json, encoding="utf-8")
        print(f"snapshot_written {snapshot_path.as_posix()}")
        return 0

    if args.dry_run:
        expected_json = snapshot_path.read_text(encoding="utf-8")
        if current_json != expected_json:
            diff = "\n".join(
                difflib.unified_diff(
                    expected_json.splitlines(),
                    current_json.splitlines(),
                    fromfile="expected_output.json",
                    tofile="current_output",
                    lineterm="",
                )
            )
            print(diff)
            return 1
        print(f"snapshot_match {demo_dir.name}")
        return 0

    print(current_json)
    return 0
