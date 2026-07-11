from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Mapping, cast

from src.alpha_quality.reporting.safety import (
    ReportPathError,
    resolve_report_file,
    validate_report_name,
)
from src.research_ledger.hash_utils import redact_secrets


class ReportArtifactNotFound(LookupError):
    pass


class ReportArtifactValidationError(ValueError):
    pass


class ReportArtifactKind(str, Enum):
    REPORT = "report"
    SCORECARD = "scorecard"
    DECISION = "decision"


@dataclass(frozen=True)
class _ArtifactContract:
    suffix: str
    schemas: frozenset[str]


_CONTRACTS: Mapping[ReportArtifactKind, _ArtifactContract] = MappingProxyType(
    {
        ReportArtifactKind.REPORT: _ArtifactContract(
            suffix=".json",
            schemas=frozenset({"alpha_genesis_report.v1", "alpha_genesis_report.v2"}),
        ),
        ReportArtifactKind.SCORECARD: _ArtifactContract(
            suffix=".scorecard.json",
            schemas=frozenset({"alpha_quality_scorecard.v1"}),
        ),
        ReportArtifactKind.DECISION: _ArtifactContract(
            suffix=".decision.json",
            schemas=frozenset(
                {
                    "alpha_quality_decision.v1",
                    "alpha_quality_decision.v2",
                    "quality_decision_artifact.v2",
                }
            ),
        ),
    }
)

_FORBIDDEN_DECISIONS = frozenset(
    {"live_candidate", "production_ready", "approved_to_trade"}
)
_RESEARCH_DECISIONS = frozenset(
    {"reject", "research_only", "candidate_zoo", "paper_candidate", "forward_track"}
)
_MAX_DEPTH = 32
_MAX_ITEMS = 20_000
_MAX_STRING_CHARS = 65_536
_REPORT_PRIVATE_KEY_PARTS = (
    "account_id",
    "account_number",
    "environment",
    "env_dump",
    "oauth_cache",
)
_PRIVATE_ABSOLUTE_PATH_RE = re.compile(
    r"(?i)^(?:[a-z]:[\\/]|\\\\|/(?:home|users|root|tmp|var|mnt|private|workspace)(?:/|$))"
)


def _reject_constant(value: str) -> None:
    raise ReportArtifactValidationError(f"non-finite JSON constant: {value}")


def _closed_object(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ReportArtifactValidationError("duplicate JSON object key")
        result[key] = value
    return result


def _validate_tree(value: Any, *, depth: int = 0, counter: list[int] | None = None) -> None:
    if depth > _MAX_DEPTH:
        raise ReportArtifactValidationError("report artifact nesting limit exceeded")
    if counter is None:
        counter = [0]
    counter[0] += 1
    if counter[0] > _MAX_ITEMS:
        raise ReportArtifactValidationError("report artifact item limit exceeded")
    if isinstance(value, float) and not math.isfinite(value):
        raise ReportArtifactValidationError("report artifact contains non-finite number")
    if isinstance(value, str) and len(value) > _MAX_STRING_CHARS:
        raise ReportArtifactValidationError("report artifact string limit exceeded")
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str) or not key:
                raise ReportArtifactValidationError("report artifact has invalid key")
            _validate_tree(child, depth=depth + 1, counter=counter)
    elif isinstance(value, list):
        for child in value:
            _validate_tree(child, depth=depth + 1, counter=counter)
    elif value is not None and not isinstance(value, (bool, int, float, str)):
        raise ReportArtifactValidationError("report artifact contains unsupported value")


def _redact_report_private_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: (
                "[redacted]"
                if any(part in key.lower().replace("-", "_") for part in _REPORT_PRIVATE_KEY_PARTS)
                else _redact_report_private_fields(child)
            )
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [_redact_report_private_fields(child) for child in value]
    if isinstance(value, str) and _PRIVATE_ABSOLUTE_PATH_RE.match(value):
        return "[redacted]"
    return value


def _validate_decision_labels(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "decision" and isinstance(child, str) and child not in _RESEARCH_DECISIONS:
                label = "forbidden live" if child in _FORBIDDEN_DECISIONS else "unknown"
                raise ReportArtifactValidationError(
                    f"report contains an {label} decision label"
                )
            _validate_decision_labels(child)
    elif isinstance(value, list):
        for child in value:
            _validate_decision_labels(child)


def _normalize_legacy_report(
    payload: dict[str, Any], artifact_id: str
) -> dict[str, Any]:
    if payload.get("schema_version") != "alpha_genesis_report.v1":
        return payload
    normalized = dict(payload)
    defaults: dict[str, Any] = {
        "report_id": artifact_id,
        "candidate_id": "[unavailable]",
        "data_scope": "unknown",
        "decision": "research_only",
        "data_snapshot_hash": None,
        "pit_contract_present": None,
        "survivorship_bias": None,
        "split_config": {},
        "tradability_metrics": {},
        "warnings": ["LEGACY_REPORT_BOUNDARY_INCOMPLETE"],
        "cap_reasons": ["RESEARCH_ONLY"],
        "limitations": [
            "legacy report omits one or more scoped evidence boundaries"
        ],
        "non_goals": ["not live trading authorization"],
    }
    synthesized: list[str] = []
    for key, value in defaults.items():
        if key not in normalized:
            normalized[key] = value
            synthesized.append(key)
    if synthesized:
        normalized["report_safety"] = {
            "schema_version": "alpha_genesis_report_safety.v1",
            "legacy_boundary_incomplete": True,
            "synthesized_fields": sorted(synthesized),
        }
    return normalized


class ReportArtifactReader:
    """Read-only gateway for already-built, root-contained report artifacts."""

    def __init__(self, root: str | Path, *, max_bytes: int = 1_048_576) -> None:
        if max_bytes < 1 or max_bytes > 8_388_608:
            raise ValueError("max_bytes must be between 1 and 8388608")
        self._root = Path(os.path.abspath(Path(root)))
        self._max_bytes = max_bytes

    @property
    def configured_root(self) -> Path:
        return self._root

    def read(self, artifact_id: str, kind: ReportArtifactKind) -> dict[str, Any]:
        contract = _CONTRACTS[kind]
        if len(artifact_id) > 128:
            raise ReportPathError("invalid report artifact id")
        validate_report_name(artifact_id)
        if not self._root.exists():
            raise ReportArtifactNotFound(artifact_id)
        try:
            path = resolve_report_file(self._root, f"{artifact_id}{contract.suffix}")
        except ReportPathError:
            raise
        if not path.exists():
            raise ReportArtifactNotFound(artifact_id)
        try:
            before = path.stat()
            size = before.st_size
            if size > self._max_bytes:
                raise ReportArtifactValidationError("report artifact size limit exceeded")
            raw = path.read_bytes()
            after = path.stat()
        except OSError as exc:
            raise ReportArtifactValidationError("report artifact cannot be read") from exc
        if (
            len(raw) != size
            or len(raw) > self._max_bytes
            or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        ):
            raise ReportArtifactValidationError("report artifact changed during bounded read")
        try:
            if resolve_report_file(self._root, path.name) != path:
                raise ReportArtifactValidationError(
                    "report artifact containment changed during read"
                )
        except ReportPathError as exc:
            raise ReportArtifactValidationError(
                "report artifact containment changed during read"
            ) from exc
        try:
            text = raw.decode("utf-8", errors="strict")
            payload = json.loads(
                text,
                parse_constant=_reject_constant,
                object_pairs_hook=_closed_object,
            )
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ReportArtifactValidationError("report artifact is invalid JSON") from exc
        if not isinstance(payload, dict):
            raise ReportArtifactValidationError("report artifact must be a JSON object")
        _validate_tree(payload)
        schema = payload.get("schema_version")
        if schema not in contract.schemas:
            raise ReportArtifactValidationError("unknown report artifact schema version")
        if kind is ReportArtifactKind.REPORT:
            payload = _normalize_legacy_report(payload, artifact_id)
        _validate_decision_labels(payload)
        if kind is ReportArtifactKind.REPORT:
            required = {
                "report_id",
                "candidate_id",
                "data_scope",
                "limitations",
                "non_goals",
                "decision",
                "data_snapshot_hash",
                "pit_contract_present",
                "survivorship_bias",
                "split_config",
                "tradability_metrics",
                "warnings",
                "cap_reasons",
            }
            if not required.issubset(payload):
                raise ReportArtifactValidationError("report omits required research boundaries")
            if (
                not isinstance(payload["limitations"], list)
                or not payload["limitations"]
                or not isinstance(payload["non_goals"], list)
                or not payload["non_goals"]
            ):
                raise ReportArtifactValidationError("report research boundaries must be non-empty")
        return cast(
            dict[str, Any],
            _redact_report_private_fields(redact_secrets(payload)),
        )
