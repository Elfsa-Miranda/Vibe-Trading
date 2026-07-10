from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

from src.alpha_foundry.reports.model import AlphaGenesisReport
from src.alpha_foundry.reports.render_markdown import render_markdown
from src.alpha_quality.flags import ResolvedAGSFlags


class AlphaGenesisCliError(RuntimeError):
    """Raised for operator-facing CLI report read/render failures."""


def load_report(path: str | Path) -> AlphaGenesisReport:
    try:
        payload: Any = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AlphaGenesisCliError("invalid Alpha Genesis report") from exc
    if not isinstance(payload, dict):
        raise AlphaGenesisCliError("invalid Alpha Genesis report")
    try:
        return AlphaGenesisReport(**payload)
    except TypeError as exc:
        raise AlphaGenesisCliError("invalid Alpha Genesis report") from exc


def render_report_file(path: str | Path, *, markdown: bool = False) -> str:
    report = load_report(path)
    if markdown:
        return render_markdown(report)
    return report.to_json()


def main(
    argv: list[str] | None = None,
    *,
    settings: Mapping[str, Any] | object | None = None,
) -> int:
    flags = ResolvedAGSFlags.from_settings(settings)
    if not flags.enabled("VIBE_TRADING_AGS_ENABLED"):
        print("Alpha Genesis research CLI is disabled", file=sys.stderr)
        return 2
    parser = argparse.ArgumentParser(description="Read Alpha Genesis research artifacts")
    parser.add_argument("report", help="Path to an Alpha Genesis report JSON file")
    parser.add_argument("--markdown", action="store_true", help="Render Markdown instead of JSON")
    args = parser.parse_args(argv)
    try:
        print(render_report_file(args.report, markdown=args.markdown))
    except AlphaGenesisCliError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
