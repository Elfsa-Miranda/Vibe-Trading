"""Immutable input references, evidence records, and Decision v2 output."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Literal, Mapping, cast

from src.research_ledger.hash_utils import canonical_json_hash

_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

EvidenceKind = Literal[
    "scorecard",
    "execution",
    "snapshot",
    "ledger",
    "mechanism",
    "complement",
    "final_test",
    "forward_plan",
]
DecisionLevel = Literal[
    "reject",
    "research_only",
    "candidate_zoo",
    "paper_candidate",
    "forward_track",
]


def _require_hash(value: str, name: str) -> None:
    if not isinstance(value, str) or _HASH_RE.fullmatch(value) is None:
        raise ValueError(f"{name} must be a canonical sha256 hash")


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw(item) for item in value]
    return value


def _validate_bool(value: Any, path: str) -> None:
    if not isinstance(value, bool):
        raise ValueError(f"{path} must be boolean")


def _validate_optional_finite(value: Any, path: str) -> None:
    if value is not None and (
        isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
    ):
        raise ValueError(f"{path} must be null or finite")


def _validate_limitations(value: Any, path: str) -> None:
    if not isinstance(value, (list, tuple)) or any(
        not isinstance(item, str) or not item or len(item) > 256 for item in value
    ):
        raise ValueError(f"{path} must be bounded strings")
    if tuple(value) != tuple(sorted(set(value))):
        raise ValueError(f"{path} must be sorted and unique")


_FIELDS: dict[EvidenceKind, dict[str, str]] = {
    "scorecard": {
        "formula_valid": "bool",
        "formula_ambiguous": "bool",
        "lookahead_detected": "bool",
        "train_valid_terminal": "bool",
        "reproducible": "bool",
        "bounded": "bool",
        "validation_rank_ic": "optional_finite",
        "regime_dependent": "bool",
        "limitations": "limitations",
    },
    "execution": {
        "available": "bool",
        "execution_alpha": "optional_finite",
        "total_cost": "optional_finite",
        "economically_nonnegative": "optional_bool",
        "limitations": "limitations",
    },
    "snapshot": {
        "pit_available": "bool",
        "survivorship_bias": "bool",
        "limitations": "limitations",
    },
    "ledger": {
        "complete": "bool",
        "terminal_train_valid": "bool",
        "reduced_durability": "bool",
        "limitations": "limitations",
    },
    "mechanism": {
        "contract_registered": "bool",
        "decisive_available": "bool",
        "ordinal_state": "mechanism_state",
        "limitations": "limitations",
    },
    "complement": {
        "status": "complement_status",
        "limitations": "limitations",
    },
    "final_test": {
        "frozen": "bool",
        "one_shot": "bool",
        "contaminated": "bool",
        "quality_passed": "bool",
        "final_oos_ic": "optional_finite",
        "limitations": "limitations",
    },
    "forward_plan": {
        "frozen": "bool",
        "minimum_observations": "positive_int",
        "success_claim": "bool",
        "limitations": "limitations",
    },
}


def _validate_payload(kind: EvidenceKind, payload: Mapping[str, Any]) -> dict[str, Any]:
    fields = _FIELDS[kind]
    if set(payload) != set(fields):
        unknown = sorted(set(payload) - set(fields))
        missing = sorted(set(fields) - set(payload))
        raise ValueError(f"closed {kind} evidence fields mismatch: unknown={unknown}, missing={missing}")
    plain = _thaw(payload)
    for name, validator in fields.items():
        value = plain[name]
        path = f"{kind}.{name}"
        if validator == "bool":
            _validate_bool(value, path)
        elif validator == "optional_bool":
            if value is not None:
                _validate_bool(value, path)
        elif validator == "optional_finite":
            _validate_optional_finite(value, path)
        elif validator == "limitations":
            _validate_limitations(value, path)
        elif validator == "positive_int":
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{path} must be a positive integer")
        elif validator == "mechanism_state":
            if value not in {"falsified", "inconclusive", "partial_support", "supported"}:
                raise ValueError(f"{path} has an unknown ordinal state")
        elif validator == "complement_status":
            if value not in {
                "duplicate",
                "unavailable",
                "insufficient",
                "nonpositive_marginal_value",
                "complementary",
            }:
                raise ValueError(f"{path} has an unknown status")
    if kind == "execution":
        available = bool(plain["available"])
        metrics = (
            plain["execution_alpha"],
            plain["total_cost"],
            plain["economically_nonnegative"],
        )
        if available != all(value is not None for value in metrics):
            raise ValueError("execution availability and metrics disagree")
    if kind == "forward_plan" and plain["success_claim"]:
        raise ValueError("a frozen forward plan cannot claim forward success")
    return cast(dict[str, Any], plain)


@dataclass(frozen=True)
class DecisionEvidenceRefs:
    factor_spec_id: str
    scorecard_hash: str
    execution_hash: str | None
    snapshot_hash: str | None
    ledger_watermark_hash: str
    mechanism_evidence_hash: str | None
    complement_evidence_hash: str | None
    final_test_artifact_hash: str | None
    forward_plan_hash: str | None

    def __post_init__(self) -> None:
        if not self.factor_spec_id or len(self.factor_spec_id) > 256:
            raise ValueError("factor_spec_id must be bounded non-empty text")
        for name in (
            "scorecard_hash",
            "ledger_watermark_hash",
            "execution_hash",
            "snapshot_hash",
            "mechanism_evidence_hash",
            "complement_evidence_hash",
            "final_test_artifact_hash",
            "forward_plan_hash",
        ):
            value = getattr(self, name)
            if value is not None:
                _require_hash(value, name)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "DecisionEvidenceRefs":
        forbidden_tokens = {
            "decision",
            "score",
            "totalqualityscore",
            "hardfailures",
            "failures",
            "warnings",
            "caps",
            "capreasons",
        }
        normalized = {
            re.sub(r"[^a-z0-9]", "", str(name).lower()): str(name) for name in value
        }
        forbidden = sorted(original for token, original in normalized.items() if token in forbidden_tokens)
        if forbidden:
            raise ValueError(f"caller decision-truth fields are forbidden: {forbidden}")
        expected = {
            "factor_spec_id",
            "scorecard_hash",
            "execution_hash",
            "snapshot_hash",
            "ledger_watermark_hash",
            "mechanism_evidence_hash",
            "complement_evidence_hash",
            "final_test_artifact_hash",
            "forward_plan_hash",
        }
        if set(value) != expected:
            raise ValueError("DecisionEvidenceRefs requires the exact closed reference fields")
        return cls(**dict(value))

    def to_dict(self) -> dict[str, str | None]:
        return {
            "factor_spec_id": self.factor_spec_id,
            "scorecard_hash": self.scorecard_hash,
            "execution_hash": self.execution_hash,
            "snapshot_hash": self.snapshot_hash,
            "ledger_watermark_hash": self.ledger_watermark_hash,
            "mechanism_evidence_hash": self.mechanism_evidence_hash,
            "complement_evidence_hash": self.complement_evidence_hash,
            "final_test_artifact_hash": self.final_test_artifact_hash,
            "forward_plan_hash": self.forward_plan_hash,
        }

    @property
    def evidence_hashes(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                value
                for name, value in self.to_dict().items()
                if name != "factor_spec_id" and value is not None
            )
        )


@dataclass(frozen=True)
class DecisionEvidenceRecord:
    schema_version: Literal["decision_evidence_record.v2"]
    evidence_kind: EvidenceKind
    factor_spec_id: str
    payload: Mapping[str, Any]
    evidence_hash: str

    def __post_init__(self) -> None:
        if self.schema_version != "decision_evidence_record.v2":
            raise ValueError("unsupported decision evidence schema")
        if self.evidence_kind not in _FIELDS:
            raise ValueError("unknown decision evidence kind")
        if not self.factor_spec_id or len(self.factor_spec_id) > 256:
            raise ValueError("factor_spec_id must be bounded non-empty text")
        validated = _validate_payload(self.evidence_kind, self.payload)
        object.__setattr__(self, "payload", _freeze(validated))
        _require_hash(self.evidence_hash, "evidence_hash")
        if self.evidence_hash != canonical_json_hash(self._content_dict()):
            raise ValueError("decision evidence hash does not match content")

    @classmethod
    def create(
        cls,
        *,
        evidence_kind: EvidenceKind,
        factor_spec_id: str,
        payload: Mapping[str, Any],
    ) -> "DecisionEvidenceRecord":
        validated = _validate_payload(evidence_kind, payload)
        content = {
            "schema_version": "decision_evidence_record.v2",
            "evidence_kind": evidence_kind,
            "factor_spec_id": factor_spec_id,
            "payload": validated,
        }
        return cls(
            schema_version="decision_evidence_record.v2",
            evidence_kind=evidence_kind,
            factor_spec_id=factor_spec_id,
            payload=validated,
            evidence_hash=canonical_json_hash(content),
        )

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "evidence_kind": self.evidence_kind,
            "factor_spec_id": self.factor_spec_id,
            "payload": _thaw(self.payload),
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._content_dict(), "evidence_hash": self.evidence_hash}


@dataclass(frozen=True)
class AlphaQualityDecisionV2:
    schema_version: Literal["alpha_quality_decision.v2"]
    factor_spec_id: str
    decision: DecisionLevel
    tier: int
    policy_version: str
    policy_hash: str
    evidence_hashes: tuple[str, ...]
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    caps: tuple[str, ...]
    limitations: tuple[str, ...]
    within_tier_score: float
    forward_success_claim: Literal[False]
    decision_hash: str

    def __post_init__(self) -> None:
        if self.schema_version != "alpha_quality_decision.v2":
            raise ValueError("unsupported Decision v2 schema")
        expected_tier = {
            "reject": 0,
            "research_only": 1,
            "candidate_zoo": 2,
            "paper_candidate": 3,
            "forward_track": 4,
        }.get(self.decision)
        if expected_tier is None or self.tier != expected_tier:
            raise ValueError("decision and tier do not match")
        _require_hash(self.policy_hash, "policy_hash")
        if not math.isfinite(self.within_tier_score):
            raise ValueError("within_tier_score must be finite")
        for name in ("evidence_hashes", "reasons", "warnings", "caps", "limitations"):
            values = getattr(self, name)
            if values != tuple(sorted(set(values))):
                raise ValueError(f"{name} must be sorted and unique")
        if self.decision == "reject" and not self.reasons:
            raise ValueError("reject requires exact reasons")
        if self.decision == "research_only" and not self.caps:
            raise ValueError("research_only requires exact caps")
        if self.forward_success_claim is not False:
            raise ValueError("Decision v2 cannot claim forward success")
        _require_hash(self.decision_hash, "decision_hash")
        if self.decision_hash != canonical_json_hash(self._content_dict()):
            raise ValueError("decision hash does not match deterministic content")

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "factor_spec_id": self.factor_spec_id,
            "decision": self.decision,
            "tier": self.tier,
            "policy_version": self.policy_version,
            "policy_hash": self.policy_hash,
            "evidence_hashes": list(self.evidence_hashes),
            "reasons": list(self.reasons),
            "warnings": list(self.warnings),
            "caps": list(self.caps),
            "limitations": list(self.limitations),
            "within_tier_score": self.within_tier_score,
            "forward_success_claim": self.forward_success_claim,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._content_dict(), "decision_hash": self.decision_hash}


__all__ = [
    "AlphaQualityDecisionV2",
    "DecisionEvidenceRecord",
    "DecisionEvidenceRefs",
    "DecisionLevel",
    "EvidenceKind",
]
