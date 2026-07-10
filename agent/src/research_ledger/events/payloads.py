"""Closed versioned payload registry and deterministic validation."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any, Callable, Mapping

from src.research_ledger.events.model import EventValidationError
from src.research_ledger.hash_utils import canonical_json, redact_secrets


_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_SAFE_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")
_MAX_PAYLOAD_BYTES = 262_144
_MAX_DEPTH = 24
_MAX_NODES = 10_000
_EVENT_PRIVATE_PATH_RE = re.compile(
    r"^(?:/(?:home|mnt|opt|private|root|tmp|Users|var|workspace)(?:/|$)|[A-Za-z]:[\\/]|\\\\)"
)
_EVENT_SENSITIVE_KEYS = frozenset(
    {"account_id", "account_ids", "env", "environ", "environment", "environment_variables", "oauth_cache"}
)

Validator = Callable[[Any, str], None]


def _string(value: Any, path: str) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > 1024:
        raise EventValidationError(f"{path} must be a non-empty bounded string")
    if any(ord(char) < 32 for char in value):
        raise EventValidationError(f"{path} contains control characters")


def _nullable_string(value: Any, path: str) -> None:
    if value is not None:
        _string(value, path)


def _hash(value: Any, path: str) -> None:
    if not isinstance(value, str) or not _HASH_RE.fullmatch(value):
        raise EventValidationError(f"{path} must be a sha256 content hash")


def _nullable_hash(value: Any, path: str) -> None:
    if value is not None:
        _hash(value, path)


def _timestamp(value: Any, path: str) -> None:
    _string(value, path)
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise EventValidationError(f"{path} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise EventValidationError(f"{path} must include a timezone")


def _integer(value: Any, path: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise EventValidationError(f"{path} must be an integer")


def _nonnegative_integer(value: Any, path: str) -> None:
    _integer(value, path)
    if value < 0:
        raise EventValidationError(f"{path} must be non-negative")


def _probability(value: Any, path: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EventValidationError(f"{path} must be numeric")
    if not math.isfinite(float(value)) or not 0.0 <= float(value) <= 1.0:
        raise EventValidationError(f"{path} must be finite and between zero and one")


def _boolean(value: Any, path: str) -> None:
    if not isinstance(value, bool):
        raise EventValidationError(f"{path} must be boolean")


def _mapping(value: Any, path: str) -> None:
    if not isinstance(value, Mapping):
        raise EventValidationError(f"{path} must be an object")


def _string_list(value: Any, path: str) -> None:
    if not isinstance(value, (list, tuple)):
        raise EventValidationError(f"{path} must be a list")
    for index, item in enumerate(value):
        _string(item, f"{path}[{index}]")


def _nonempty_string_list(value: Any, path: str) -> None:
    _string_list(value, path)
    if not value:
        raise EventValidationError(f"{path} must not be empty")


def _artifact_list(value: Any, path: str) -> None:
    if not isinstance(value, (list, tuple)):
        raise EventValidationError(f"{path} must be a list")
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise EventValidationError(f"{path}[{index}] must be an object")
        expected = {"relative_path", "artifact_hash", "media_type"}
        if set(item) != expected:
            raise EventValidationError(f"{path}[{index}] has unknown artifact fields")
        _string(item["relative_path"], f"{path}[{index}].relative_path")
        _hash(item["artifact_hash"], f"{path}[{index}].artifact_hash")
        _string(item["media_type"], f"{path}[{index}].media_type")


def _enum(*values: str) -> Validator:
    allowed = frozenset(values)

    def validate(value: Any, path: str) -> None:
        if value not in allowed:
            raise EventValidationError(f"{path} must be one of {sorted(allowed)}")

    return validate


def _reason_codes(value: Any, path: str) -> None:
    _string_list(value, path)
    for item in value:
        if not _SAFE_CODE_RE.fullmatch(item):
            raise EventValidationError(f"{path} contains an invalid reason code")


@dataclass(frozen=True)
class PayloadSpec:
    version: str
    fields: Mapping[str, Validator]

    def __post_init__(self) -> None:
        object.__setattr__(self, "fields", MappingProxyType(dict(self.fields)))


_DATA_SCOPE = _enum("train", "valid", "train_valid", "test", "final_test", "forward", "demo_fixture")
_DECISION = _enum(
    "reject",
    "research_only",
    "candidate_zoo",
    "paper_candidate",
    "forward_track",
    "none",
)

_PAYLOAD_SPECS: dict[str, PayloadSpec] = {
    "TrialStarted": PayloadSpec(
        "trial_started.v1",
        {
            "trial_id": _string,
            "candidate_id": _string,
            "data_scope": _DATA_SCOPE,
            "objective": _string,
            "started_at": _timestamp,
        },
    ),
    "FactorDefinitionRecorded": PayloadSpec(
        "factor_definition_recorded.v1",
        {
            "factor_spec_id": _string,
            "expression_id": _string,
            "canonical_ast_hash": _hash,
            "grammar_version": _string,
            "grammar_hash": _hash,
            "metadata": _mapping,
            "artifact_refs": _artifact_list,
        },
    ),
    "DerivationRecorded": PayloadSpec(
        "derivation_recorded.v1",
        {
            "child_factor_spec_id": _string,
            "parent_factor_spec_ids": _nonempty_string_list,
            "trial_terminal_event_hash": _hash,
            "derivation_kind": _enum("mutation", "crossover", "manual_registered"),
        },
    ),
    "GenerationFailureRecorded": PayloadSpec(
        "generation_failure_recorded.v1",
        {
            "trial_id": _string,
            "failure_code": _string,
            "failure_kind": _enum("invalid", "timeout", "error", "infrastructure_failure"),
            "message": _string,
            "occurred_at": _timestamp,
        },
    ),
    "EvaluationRecorded": PayloadSpec(
        "evaluation_recorded.v1",
        {
            "evaluation_id": _string,
            "trial_id": _string,
            "factor_spec_id": _string,
            "data_scope": _DATA_SCOPE,
            "scorecard_hash": _hash,
            "artifact_refs": _artifact_list,
            "metadata": _mapping,
        },
    ),
    "TrialTerminated": PayloadSpec(
        "trial_terminated.v1",
        {
            "trial_id": _string,
            "status": _enum(
                "success",
                "reject",
                "skip",
                "invalid",
                "duplicate",
                "timeout",
                "error",
                "infrastructure_failure",
            ),
            "reason_codes": _reason_codes,
            "decision": _DECISION,
            "evaluation_event_hash": _nullable_hash,
            "terminated_at": _timestamp,
        },
    ),
    "RetrieverDecisionRecorded": PayloadSpec(
        "retriever_decision_recorded.v1",
        {
            "decision_id": _string,
            "selected_factor_spec_ids": _string_list,
            "selection_propensity": _probability,
            "seed": _integer,
            "policy_hash": _hash,
            "eligible_event_watermark": _nullable_hash,
            "veto_reason": _nullable_string,
        },
    ),
    "FalsificationContractRegistered": PayloadSpec(
        "falsification_contract_registered.v1",
        {
            "contract_id": _string,
            "contract_hash": _hash,
            "factor_spec_id": _string,
            "registered_at": _timestamp,
            "data_access_cutoff": _timestamp,
            "policy_hash": _hash,
        },
    ),
    "FalsificationResultRecorded": PayloadSpec(
        "falsification_result_recorded.v1",
        {
            "result_id": _string,
            "contract_id": _string,
            "contract_hash": _hash,
            "outcome": _enum("falsified", "inconclusive", "partial_support", "supported"),
            "artifact_refs": _artifact_list,
        },
    ),
    "QualityDecisionRecorded": PayloadSpec(
        "quality_decision_recorded.v1",
        {
            "decision_id": _string,
            "factor_spec_id": _string,
            "decision": _DECISION,
            "policy_hash": _hash,
            "evidence_hashes": _string_list,
            "reasons": _reason_codes,
            "warnings": _reason_codes,
            "caps": _reason_codes,
            "limitations": _string_list,
        },
    ),
    "ForwardPlanRecorded": PayloadSpec(
        "forward_plan_recorded.v1",
        {
            "plan_id": _string,
            "factor_spec_id": _string,
            "plan_hash": _hash,
            "minimum_observations": _nonnegative_integer,
            "policy_hash": _hash,
        },
    ),
    "ForwardObservationRecorded": PayloadSpec(
        "forward_observation_recorded.v1",
        {
            "observation_id": _string,
            "plan_id": _string,
            "period_start": _timestamp,
            "period_end": _timestamp,
            "observation_hash": _hash,
            "previous_observation_hash": _nullable_hash,
            "artifact_refs": _artifact_list,
        },
    ),
}
PAYLOAD_SPECS: Mapping[str, PayloadSpec] = MappingProxyType(_PAYLOAD_SPECS)


def _check_finite_and_bounds(value: Any, *, path: str = "payload", depth: int = 0) -> int:
    if depth > _MAX_DEPTH:
        raise EventValidationError("payload exceeds maximum depth")
    nodes = 1
    if isinstance(value, float) and not math.isfinite(value):
        raise EventValidationError(f"{path} contains a non-finite value")
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise EventValidationError(f"{path} keys must be strings")
            nodes += _check_finite_and_bounds(item, path=f"{path}.{key}", depth=depth + 1)
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            nodes += _check_finite_and_bounds(item, path=f"{path}[{index}]", depth=depth + 1)
    elif value is not None and not isinstance(value, (str, int, float, bool)):
        raise EventValidationError(f"{path} contains unsupported JSON type {type(value).__name__}")
    if nodes > _MAX_NODES:
        raise EventValidationError("payload exceeds maximum node count")
    return nodes


def _plain_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain_json(item) for item in value]
    return value


def _event_redact(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            normalized = str(key).lower().replace("-", "_")
            if normalized in _EVENT_SENSITIVE_KEYS:
                redacted[str(key)] = "[redacted]"
            else:
                redacted[str(key)] = _event_redact(item)
        return redacted
    if isinstance(value, list):
        return [_event_redact(item) for item in value]
    if isinstance(value, str) and _EVENT_PRIVATE_PATH_RE.match(value):
        return "[redacted]"
    return value


def validate_and_redact_payload(
    event_type: str,
    payload_schema_version: str,
    raw_payload: Mapping[str, Any],
) -> dict[str, Any]:
    spec = PAYLOAD_SPECS.get(event_type)
    if spec is None:
        raise EventValidationError(f"unknown event type: {event_type}")
    if payload_schema_version != spec.version:
        raise EventValidationError(
            f"invalid payload schema version for {event_type}: {payload_schema_version}"
        )
    if not isinstance(raw_payload, Mapping):
        raise EventValidationError("payload must be an object")
    _check_finite_and_bounds(raw_payload)
    payload = _event_redact(redact_secrets(_plain_json(raw_payload)))
    expected = set(spec.fields)
    supplied = set(payload)
    unknown = sorted(supplied - expected)
    missing = sorted(expected - supplied)
    if unknown:
        raise EventValidationError(f"unknown payload fields: {unknown}")
    if missing:
        raise EventValidationError(f"missing payload fields: {missing}")
    for name, validator in spec.fields.items():
        validator(payload[name], f"payload.{name}")
    encoded = canonical_json(payload).encode("utf-8")
    if len(encoded) > _MAX_PAYLOAD_BYTES:
        raise EventValidationError("payload exceeds maximum encoded size")
    _validate_cross_field_rules(event_type, payload)
    return payload


def _validate_cross_field_rules(event_type: str, payload: Mapping[str, Any]) -> None:
    if event_type == "TrialTerminated":
        status = payload["status"]
        decision = payload["decision"]
        if status in {"skip", "invalid", "duplicate", "timeout", "error", "infrastructure_failure"}:
            if decision not in {"none", "reject", "research_only"}:
                raise EventValidationError(f"{status} terminal outcome cannot promote a candidate")
        if status == "reject" and decision not in {"none", "reject"}:
            raise EventValidationError("reject terminal outcome cannot promote a candidate")
        if status == "success" and decision == "none":
            raise EventValidationError("success terminal outcome requires a research decision")
    if event_type == "ForwardPlanRecorded" and payload["minimum_observations"] <= 0:
        raise EventValidationError("minimum_observations must be positive")


def envelope_diagnostics(
    event_type: str,
    payload: Mapping[str, Any],
    *,
    reduced_durability: bool,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    warnings: set[str] = set()
    hard_failures: set[str] = set()
    if reduced_durability:
        warnings.add("REDUCED_DURABILITY")
    if event_type == "GenerationFailureRecorded":
        hard_failures.add(str(payload["failure_code"]))
    if event_type == "TrialTerminated":
        codes = {str(code) for code in payload["reason_codes"]}
        if payload["status"] == "skip":
            warnings |= codes
        elif payload["status"] != "success":
            hard_failures |= codes
    if event_type == "FalsificationResultRecorded" and payload["outcome"] == "inconclusive":
        warnings.add("FALSIFICATION_INCONCLUSIVE")
    if event_type == "QualityDecisionRecorded":
        warnings |= {str(code) for code in payload["warnings"]}
        warnings |= {str(code) for code in payload["caps"]}
        if payload["decision"] == "reject":
            hard_failures |= {str(code) for code in payload["reasons"]}
    return tuple(sorted(warnings)), tuple(sorted(hard_failures))


__all__ = ["PAYLOAD_SPECS", "envelope_diagnostics", "validate_and_redact_payload"]
