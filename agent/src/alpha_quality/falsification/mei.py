"""Deterministic ordinal mechanism-evidence aggregation.

``MechanismEvidenceIndex.v1`` is deliberately an ordinal classification.  It
does not serialize test statistics, p/e-values, or any probability-like
quantity.  Detailed statistical evidence remains in the immutable result
artifacts referenced by their hashes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, Sequence

from src.research_ledger.hash_utils import canonical_json_hash

EvidenceState = Literal[
    "falsified",
    "contradiction",
    "inconclusive",
    "missing",
    "unavailable",
    "low_power",
    "partial_support",
    "supported",
]
OrdinalMechanismState = Literal[
    "falsified", "inconclusive", "partial_support", "supported"
]

MECHANISM_EVIDENCE_SCHEMA_VERSION: Literal["mechanism_evidence_index.v1"] = (
    "mechanism_evidence_index.v1"
)
MECHANISM_EVIDENCE_TRUTH_TABLE_VERSION: Literal[
    "mechanism_evidence_truth_table.v1"
] = "mechanism_evidence_truth_table.v1"

_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_EVIDENCE_STATES = frozenset(
    {
        "falsified",
        "contradiction",
        "inconclusive",
        "missing",
        "unavailable",
        "low_power",
        "partial_support",
        "supported",
    }
)
_DECISIVE_INCONCLUSIVE_STATES = frozenset(
    {"inconclusive", "missing", "unavailable", "low_power", "partial_support"}
)


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty text")


def _require_hash(value: str, field_name: str) -> None:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a canonical sha256 hash")


def _normalize_codes(values: Sequence[str], field_name: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ValueError(f"{field_name} must be a sequence of codes")
    normalized: set[str] = set()
    for value in values:
        _require_text(value, field_name)
        normalized.add(value.strip())
    return tuple(sorted(normalized))


@dataclass(frozen=True)
class MechanismEvidenceRef:
    """Immutable reference to one deterministic mechanism-result artifact."""

    factor_spec_id: str
    result_hash: str
    event_hash: str
    policy_version: str
    policy_hash: str
    outcome: EvidenceState
    decisive: bool
    reason_codes: tuple[str, ...] = ()
    warning_codes: tuple[str, ...] = ()
    limitation_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.factor_spec_id, "factor_spec_id")
        _require_hash(self.result_hash, "result_hash")
        _require_hash(self.event_hash, "event_hash")
        _require_text(self.policy_version, "policy_version")
        _require_hash(self.policy_hash, "policy_hash")
        if self.outcome not in _EVIDENCE_STATES:
            raise ValueError("outcome is not a closed mechanism-evidence state")
        if not isinstance(self.decisive, bool):
            raise ValueError("decisive must be boolean")
        object.__setattr__(
            self, "reason_codes", _normalize_codes(self.reason_codes, "reason_codes")
        )
        object.__setattr__(
            self, "warning_codes", _normalize_codes(self.warning_codes, "warning_codes")
        )
        object.__setattr__(
            self,
            "limitation_codes",
            _normalize_codes(self.limitation_codes, "limitation_codes"),
        )


@dataclass(frozen=True)
class MechanismEvidenceIndex:
    """Content-addressed ordinal v1 aggregation result."""

    schema_version: Literal["mechanism_evidence_index.v1"]
    truth_table_version: Literal["mechanism_evidence_truth_table.v1"]
    factor_spec_id: str
    ordinal_state: OrdinalMechanismState
    policy_version: str
    policy_hash: str
    source_result_hashes: tuple[str, ...]
    source_event_hashes: tuple[str, ...]
    decisive_event_hashes: tuple[str, ...]
    advisory_event_hashes: tuple[str, ...]
    reason_codes: tuple[str, ...]
    warning_codes: tuple[str, ...]
    limitation_codes: tuple[str, ...]
    mei_hash: str

    def __post_init__(self) -> None:
        if self.schema_version != MECHANISM_EVIDENCE_SCHEMA_VERSION:
            raise ValueError("unsupported mechanism-evidence schema")
        if self.truth_table_version != MECHANISM_EVIDENCE_TRUTH_TABLE_VERSION:
            raise ValueError("unsupported mechanism-evidence truth table")
        _require_text(self.factor_spec_id, "factor_spec_id")
        _require_text(self.policy_version, "policy_version")
        _require_hash(self.policy_hash, "policy_hash")
        if self.ordinal_state not in {
            "falsified",
            "inconclusive",
            "partial_support",
            "supported",
        }:
            raise ValueError("ordinal_state is not a closed v1 state")
        for field_name in (
            "source_result_hashes",
            "source_event_hashes",
            "decisive_event_hashes",
            "advisory_event_hashes",
        ):
            values = getattr(self, field_name)
            if values != tuple(sorted(set(values))):
                raise ValueError(f"{field_name} must be sorted and unique")
            for value in values:
                _require_hash(value, field_name)
        if set(self.decisive_event_hashes) & set(self.advisory_event_hashes):
            raise ValueError("an event cannot be both decisive and advisory")
        if set(self.decisive_event_hashes) | set(self.advisory_event_hashes) != set(
            self.source_event_hashes
        ):
            raise ValueError("decisive/advisory partitions must cover source events")
        for field_name in ("reason_codes", "warning_codes", "limitation_codes"):
            values = getattr(self, field_name)
            if values != _normalize_codes(values, field_name):
                raise ValueError(f"{field_name} must be sorted and unique")
        _require_hash(self.mei_hash, "mei_hash")
        if self.mei_hash != canonical_json_hash(self._content_dict()):
            raise ValueError("mei_hash does not match ordinal evidence content")

    @property
    def outcome(self) -> OrdinalMechanismState:
        """Compatibility name for consumers of fixed-family outcomes."""

        return self.ordinal_state

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "truth_table_version": self.truth_table_version,
            "factor_spec_id": self.factor_spec_id,
            "ordinal_state": self.ordinal_state,
            "policy_version": self.policy_version,
            "policy_hash": self.policy_hash,
            "source_result_hashes": list(self.source_result_hashes),
            "source_event_hashes": list(self.source_event_hashes),
            "decisive_event_hashes": list(self.decisive_event_hashes),
            "advisory_event_hashes": list(self.advisory_event_hashes),
            "reason_codes": list(self.reason_codes),
            "warning_codes": list(self.warning_codes),
            "limitation_codes": list(self.limitation_codes),
        }

    def to_dict(self) -> dict[str, object]:
        payload = self._content_dict()
        payload["mei_hash"] = self.mei_hash
        return payload


def _deduplicate(evidence: Sequence[MechanismEvidenceRef]) -> tuple[MechanismEvidenceRef, ...]:
    by_result: dict[str, MechanismEvidenceRef] = {}
    by_event: dict[str, MechanismEvidenceRef] = {}
    for item in evidence:
        if not isinstance(item, MechanismEvidenceRef):
            raise TypeError("mechanism evidence must use immutable evidence references")
        prior_result = by_result.get(item.result_hash)
        if prior_result is not None and prior_result != item:
            raise ValueError("conflicting evidence reuses a result hash")
        prior_event = by_event.get(item.event_hash)
        if prior_event is not None and prior_event != item:
            raise ValueError("conflicting evidence reuses an event hash")
        by_result[item.result_hash] = item
        by_event[item.event_hash] = item
    return tuple(sorted(by_result.values(), key=lambda item: (item.result_hash, item.event_hash)))


def _classify(evidence: tuple[MechanismEvidenceRef, ...]) -> tuple[OrdinalMechanismState, str]:
    decisive = tuple(item for item in evidence if item.decisive)
    if any(item.outcome in {"falsified", "contradiction"} for item in decisive):
        return "falsified", "DECISIVE_MECHANISM_CONTRADICTION"
    if not decisive:
        return "inconclusive", "NO_DECISIVE_EVIDENCE"
    decisive_gaps = {item.outcome for item in decisive} & _DECISIVE_INCONCLUSIVE_STATES
    if decisive_gaps:
        if "missing" in decisive_gaps:
            return "inconclusive", "DECISIVE_EVIDENCE_MISSING"
        if "unavailable" in decisive_gaps:
            return "inconclusive", "DECISIVE_TEST_UNAVAILABLE"
        if "low_power" in decisive_gaps:
            return "inconclusive", "DECISIVE_TEST_LOW_POWER"
        return "inconclusive", "DECISIVE_TEST_INCONCLUSIVE"
    if all(item.outcome == "supported" for item in evidence):
        return "supported", "ALL_INCLUDED_EVIDENCE_SUPPORTED"
    return "partial_support", "DECISIVE_SUPPORT_WITH_ADVISORY_GAPS"


def aggregate_mechanism_evidence(
    evidence: Sequence[MechanismEvidenceRef],
    *,
    factor_spec_id: str,
    policy_version: str,
    policy_hash: str,
) -> MechanismEvidenceIndex:
    """Apply the frozen v1 non-compensatory truth table."""

    _require_text(factor_spec_id, "factor_spec_id")
    _require_text(policy_version, "policy_version")
    _require_hash(policy_hash, "policy_hash")
    if not evidence:
        raise ValueError("at least one mechanism evidence reference is required")
    unique = _deduplicate(evidence)
    for item in unique:
        if item.factor_spec_id != factor_spec_id:
            raise ValueError("mechanism evidence factor mismatch")
        if item.policy_version != policy_version or item.policy_hash != policy_hash:
            raise ValueError("mechanism evidence policy mismatch")

    ordinal_state, classification_reason = _classify(unique)
    reasons = {classification_reason}
    warnings: set[str] = set()
    limitations: set[str] = set()
    for item in unique:
        reasons.update(item.reason_codes)
        warnings.update(item.warning_codes)
        limitations.update(item.limitation_codes)
        if item.outcome == "missing":
            limitations.add("MECHANISM_EVIDENCE_MISSING")
        elif item.outcome == "unavailable":
            limitations.add("MECHANISM_TEST_UNAVAILABLE")
        elif item.outcome == "low_power":
            limitations.add("MECHANISM_TEST_LOW_POWER")
        elif not item.decisive and item.outcome in {
            "falsified",
            "contradiction",
            "inconclusive",
            "partial_support",
        }:
            warnings.add("ADVISORY_EVIDENCE_NOT_FULLY_SUPPORTIVE")

    source_result_hashes = tuple(sorted(item.result_hash for item in unique))
    source_event_hashes = tuple(sorted(item.event_hash for item in unique))
    decisive_event_hashes = tuple(sorted(item.event_hash for item in unique if item.decisive))
    advisory_event_hashes = tuple(sorted(item.event_hash for item in unique if not item.decisive))
    reason_codes = tuple(sorted(reasons))
    warning_codes = tuple(sorted(warnings))
    limitation_codes = tuple(sorted(limitations))
    content: dict[str, object] = {
        "schema_version": MECHANISM_EVIDENCE_SCHEMA_VERSION,
        "truth_table_version": MECHANISM_EVIDENCE_TRUTH_TABLE_VERSION,
        "factor_spec_id": factor_spec_id,
        "ordinal_state": ordinal_state,
        "policy_version": policy_version,
        "policy_hash": policy_hash,
        "source_result_hashes": list(source_result_hashes),
        "source_event_hashes": list(source_event_hashes),
        "decisive_event_hashes": list(decisive_event_hashes),
        "advisory_event_hashes": list(advisory_event_hashes),
        "reason_codes": list(reason_codes),
        "warning_codes": list(warning_codes),
        "limitation_codes": list(limitation_codes),
    }
    return MechanismEvidenceIndex(
        schema_version=MECHANISM_EVIDENCE_SCHEMA_VERSION,
        truth_table_version=MECHANISM_EVIDENCE_TRUTH_TABLE_VERSION,
        factor_spec_id=factor_spec_id,
        ordinal_state=ordinal_state,
        policy_version=policy_version,
        policy_hash=policy_hash,
        source_result_hashes=source_result_hashes,
        source_event_hashes=source_event_hashes,
        decisive_event_hashes=decisive_event_hashes,
        advisory_event_hashes=advisory_event_hashes,
        reason_codes=reason_codes,
        warning_codes=warning_codes,
        limitation_codes=limitation_codes,
        mei_hash=canonical_json_hash(content),
    )


__all__ = [
    "EvidenceState",
    "MECHANISM_EVIDENCE_SCHEMA_VERSION",
    "MECHANISM_EVIDENCE_TRUTH_TABLE_VERSION",
    "MechanismEvidenceIndex",
    "MechanismEvidenceRef",
    "OrdinalMechanismState",
    "aggregate_mechanism_evidence",
]
