"""Strict deterministic validation-utility extraction from immutable scorecards."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Mapping


SCORECARD_MEDIA_TYPE = "application/vnd.vibe.alpha-quality-scorecard+json"


def mean_valid_rank_icir_utility(
    path: Path,
    *,
    expected_factor_spec_id: str,
    expected_data_snapshot_hash: str,
) -> float:
    try:
        scorecard = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("scorecard artifact is not strict JSON") from exc
    if not isinstance(scorecard, Mapping) or scorecard.get("schema_version") != "alpha_quality_scorecard.v1":
        raise ValueError("unsupported scorecard artifact schema")
    if scorecard.get("factor_id") != expected_factor_spec_id or scorecard.get("scope") != "discovery":
        raise ValueError("scorecard factor or scope does not match process evidence")
    if scorecard.get("data_snapshot_ref") != expected_data_snapshot_hash:
        raise ValueError("scorecard data snapshot does not match frozen action")
    try:
        by_horizon = scorecard["predictive"]["by_horizon"]
        values = [
            float(item["by_split"]["valid"]["rank_icir"])
            for item in by_horizon.values()
            if item["by_split"].get("valid", {}).get("rank_icir") is not None
        ]
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ValueError("scorecard lacks valid RankICIR evidence") from exc
    if not values or any(not math.isfinite(value) for value in values):
        raise ValueError("scorecard validation utility is unavailable or non-finite")
    return sum(values) / len(values)


def _reject_json_constant(value: str) -> Any:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


__all__ = ["SCORECARD_MEDIA_TYPE", "mean_valid_rank_icir_utility"]
