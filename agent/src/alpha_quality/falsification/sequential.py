"""Sequentially valid, bounded-mean mechanism evidence.

This module deliberately does not share the fixed-horizon executor API.  A
sequential look accepts only previously unobserved, bounded observations.  It
computes its e-values internally; caller supplied p-values, e-values, stopping
decisions, and boundaries are never evidence.

The v1 process is a finite mixture of predictable betting martingales.  For a
bounded, oriented observation ``X`` and a frozen null boundary ``delta``, each
component updates by ``E_t = E_(t-1) * (1 + lambda * Z_t)`` where ``Z_t`` is
scaled to ``[-1, 1]``.  Under the corresponding conditional-mean null this is
a non-negative supermartingale, so the frozen ``1 / alpha`` boundary has the
usual Ville anytime-error guarantee.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final, Literal, Sequence

from src.alpha_quality.falsification.policy import (
    APPROVED_SEQUENTIAL_METHOD,
    SEQUENTIAL_STOPPING_RULE,
)
from src.alpha_quality.flags import ResolvedAGSFlags
from src.research_ledger.hash_utils import canonical_json_hash

APPROVED_METHOD: Final[Literal["bounded_mean_mixture_e.v1"]] = APPROVED_SEQUENTIAL_METHOD
APPROVED_STOPPING_RULE: Final[Literal["e_process_boundary_or_max_looks.v1"]] = (
    SEQUENTIAL_STOPPING_RULE
)
VALIDATION_SCOPE: Final[Literal["valid"]] = "valid"

SequentialStatus = Literal[
    "continue",
    "support_boundary_crossed",
    "contradiction_boundary_crossed",
    "max_looks_reached",
]
StopReason = Literal["NONE", "SUPPORT_BOUNDARY", "CONTRADICTION_BOUNDARY", "MAX_LOOKS"]

_DEFAULT_LAMBDAS = (0.05, 0.1, 0.2, 0.4, 0.8)
_DEFAULT_WEIGHTS = (0.2, 0.2, 0.2, 0.2, 0.2)
_MAX_LOOKS = 10_000
_MAX_BLOCK_SIZE = 100_000
_MAX_TOTAL_OBSERVATIONS = 1_000_000
_LOG_MAX_FLOAT = math.log(float.fromhex("0x1.fffffffffffffp+1023"))


class UnsupportedSequentialMethod(ValueError):
    """The requested design has no approved v1 anytime-valid implementation."""


def _require_digest(value: str, *, name: str) -> None:
    if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != 71:
        raise ValueError(f"{name} must be a sha256 content hash")
    try:
        int(value[7:], 16)
    except ValueError as exc:
        raise ValueError(f"{name} must be a sha256 content hash") from exc


def _finite(value: float, *, name: str) -> float:
    converted = float(value)
    if not math.isfinite(converted):
        raise ValueError(f"{name} must be finite")
    return converted


def _logsumexp(values: Sequence[float]) -> float:
    maximum = max(values)
    return maximum + math.log(math.fsum(math.exp(value - maximum) for value in values))


def _mixture_log_evidence(component_logs: Sequence[float], weights: Sequence[float]) -> float:
    return _logsumexp(tuple(math.log(weight) + value for weight, value in zip(weights, component_logs, strict=True)))


def _reported_e_value(log_evidence: float) -> float:
    # The log evidence remains authoritative.  This bounded conversion keeps
    # report serialization finite even for very long approved protocols.
    return math.exp(min(log_evidence, _LOG_MAX_FLOAT))


@dataclass(frozen=True)
class SequentialProtocol:
    """A frozen validation-only sequential protocol.

    ``block_schedule`` identifies predictable blocks before their values are
    observed.  It has exactly ``maximum_looks`` unique entries; changing the
    schedule, stopping rule, method, allocation, or maximum looks changes the
    protocol hash and therefore cannot continue an existing state.
    """

    factor_spec_id: str
    snapshot_hash: str
    manifest_hash: str
    filtration_hash: str
    policy_hash: str
    block_schedule: tuple[str, ...]
    maximum_looks: int
    expected_direction: Literal["positive", "negative"]
    lower_bound: float
    upper_bound: float
    sesoi: float
    family_alpha: float = 0.05
    support_alpha: float = 0.025
    contradiction_alpha: float = 0.025
    minimum_block_size: int = 1
    scope: Literal["valid"] = VALIDATION_SCOPE
    method: Literal["bounded_mean_mixture_e.v1"] = APPROVED_METHOD
    stopping_rule: Literal["e_process_boundary_or_max_looks.v1"] = APPROVED_STOPPING_RULE
    lambda_grid: tuple[float, ...] = _DEFAULT_LAMBDAS
    mixture_weights: tuple[float, ...] = _DEFAULT_WEIGHTS
    decisive: bool = True

    def __post_init__(self) -> None:
        if (
            not isinstance(self.factor_spec_id, str)
            or not self.factor_spec_id.strip()
            or len(self.factor_spec_id) > 256
        ):
            raise ValueError("factor_spec_id is required")
        for name in ("snapshot_hash", "manifest_hash", "filtration_hash", "policy_hash"):
            _require_digest(getattr(self, name), name=name)
        if self.scope != VALIDATION_SCOPE:
            raise ValueError("sequential evidence is validation-only")
        if self.method != APPROVED_METHOD:
            raise UnsupportedSequentialMethod(f"unsupported sequential method: {self.method}")
        if self.stopping_rule != APPROVED_STOPPING_RULE:
            raise UnsupportedSequentialMethod(f"unsupported or post-hoc stopping rule: {self.stopping_rule}")
        if self.expected_direction not in {"positive", "negative"}:
            raise ValueError("expected_direction must be positive or negative")
        lower = _finite(self.lower_bound, name="lower_bound")
        upper = _finite(self.upper_bound, name="upper_bound")
        sesoi = _finite(self.sesoi, name="sesoi")
        object.__setattr__(self, "lower_bound", lower)
        object.__setattr__(self, "upper_bound", upper)
        object.__setattr__(self, "sesoi", sesoi)
        if not lower < upper:
            raise ValueError("lower_bound must be less than upper_bound")
        if sesoi < 0:
            raise ValueError("sesoi must be non-negative")
        if not isinstance(self.maximum_looks, int) or isinstance(self.maximum_looks, bool) or not 2 <= self.maximum_looks <= _MAX_LOOKS:
            raise ValueError("maximum_looks is outside the supported range")
        if not isinstance(self.minimum_block_size, int) or isinstance(self.minimum_block_size, bool) or not 1 <= self.minimum_block_size <= _MAX_BLOCK_SIZE:
            raise ValueError("minimum_block_size is outside the supported range")
        if isinstance(self.block_schedule, (str, bytes)):
            raise ValueError("block_schedule must be a sequence of block IDs")
        schedule = tuple(self.block_schedule)
        object.__setattr__(self, "block_schedule", schedule)
        if len(schedule) != self.maximum_looks:
            raise ValueError("block_schedule must freeze exactly maximum_looks blocks")
        if any(
            not isinstance(block_id, str)
            or not block_id.strip()
            or len(block_id) > 256
            for block_id in schedule
        ):
            raise ValueError("block_schedule entries must be non-empty strings")
        if len(set(schedule)) != len(schedule):
            raise ValueError("block_schedule entries must be unique")
        alphas = tuple(_finite(value, name="alpha allocation") for value in (self.family_alpha, self.support_alpha, self.contradiction_alpha))
        if not all(0 < value < 0.5 for value in alphas):
            raise ValueError("alpha allocations must be in (0, 0.5)")
        if not all(math.isfinite(1.0 / value) for value in alphas):
            raise ValueError("alpha allocations must define finite stopping boundaries")
        object.__setattr__(self, "family_alpha", alphas[0])
        object.__setattr__(self, "support_alpha", alphas[1])
        object.__setattr__(self, "contradiction_alpha", alphas[2])
        if self.support_alpha + self.contradiction_alpha > self.family_alpha + 1e-15:
            raise ValueError("sequential channel allocations exceed frozen family alpha")
        if not self.lambda_grid or len(self.lambda_grid) != len(self.mixture_weights):
            raise ValueError("lambda_grid and mixture_weights must be non-empty and aligned")
        lambdas = tuple(_finite(value, name="lambda") for value in self.lambda_grid)
        weights = tuple(_finite(value, name="mixture weight") for value in self.mixture_weights)
        if any(not 0 < value < 1 for value in lambdas) or len(set(lambdas)) != len(lambdas):
            raise ValueError("lambda_grid must contain unique values in (0, 1)")
        if any(value <= 0 for value in weights) or not math.isclose(math.fsum(weights), 1.0, abs_tol=1e-12, rel_tol=0.0):
            raise ValueError("mixture_weights must be positive and sum to one")
        object.__setattr__(self, "lambda_grid", lambdas)
        object.__setattr__(self, "mixture_weights", weights)
        if not isinstance(self.decisive, bool):
            raise ValueError("decisive must be boolean")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "sequential_protocol.v1",
            "factor_spec_id": self.factor_spec_id,
            "snapshot_hash": self.snapshot_hash,
            "manifest_hash": self.manifest_hash,
            "filtration_hash": self.filtration_hash,
            "policy_hash": self.policy_hash,
            "block_schedule": list(self.block_schedule),
            "maximum_looks": self.maximum_looks,
            "expected_direction": self.expected_direction,
            "lower_bound": self.lower_bound,
            "upper_bound": self.upper_bound,
            "sesoi": self.sesoi,
            "family_alpha": self.family_alpha,
            "support_alpha": self.support_alpha,
            "contradiction_alpha": self.contradiction_alpha,
            "minimum_block_size": self.minimum_block_size,
            "scope": self.scope,
            "method": self.method,
            "stopping_rule": self.stopping_rule,
            "lambda_grid": list(self.lambda_grid),
            "mixture_weights": list(self.mixture_weights),
            "decisive": self.decisive,
        }

    @property
    def protocol_hash(self) -> str:
        return canonical_json_hash(self.to_dict())

    @property
    def contract_hash(self) -> str:
        """Compatibility name for event schemas that call protocols contracts."""

        return self.protocol_hash

    @property
    def protocol_id(self) -> str:
        return "sequential-" + self.protocol_hash.removeprefix("sha256:")[:16]

    @property
    def block_schedule_hash(self) -> str:
        return canonical_json_hash(
            {
                "schema_version": "sequential_block_schedule.v1",
                "manifest_hash": self.manifest_hash,
                "filtration_hash": self.filtration_hash,
                "block_schedule": list(self.block_schedule),
            }
        )

    @property
    def support_boundary(self) -> float:
        return 1.0 / self.support_alpha

    @property
    def support_log_boundary(self) -> float:
        return -math.log(self.support_alpha)

    @property
    def contradiction_boundary(self) -> float:
        return 1.0 / self.contradiction_alpha

    @property
    def contradiction_log_boundary(self) -> float:
        return -math.log(self.contradiction_alpha)


SequentialContract = SequentialProtocol


@dataclass(frozen=True)
class SequentialBlock:
    """One predictable block of previously unobserved bounded outcomes."""

    block_id: str
    information_time: int
    snapshot_hash: str
    manifest_hash: str
    filtration_hash: str
    scope: Literal["valid"]
    observations: tuple[tuple[str, float], ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.block_id, str)
            or not self.block_id.strip()
            or len(self.block_id) > 256
        ):
            raise ValueError("block_id is required")
        if not isinstance(self.information_time, int) or isinstance(self.information_time, bool) or self.information_time < 1:
            raise ValueError("information_time must be a positive integer")
        for name in ("snapshot_hash", "manifest_hash", "filtration_hash"):
            _require_digest(getattr(self, name), name=name)
        if self.scope != VALIDATION_SCOPE:
            raise ValueError("sequential blocks are validation-only")
        if not self.observations or len(self.observations) > _MAX_BLOCK_SIZE:
            raise ValueError("sequential block size is outside the supported range")
        normalized: list[tuple[str, float]] = []
        for item in self.observations:
            if not isinstance(item, (tuple, list)) or len(item) != 2:
                raise ValueError("observations must be (unit_hash, raw_value) pairs")
            unit_hash, value = item
            _require_digest(unit_hash, name="observation unit_hash")
            normalized.append((unit_hash, _finite(value, name="observation value")))
        normalized.sort(key=lambda item: item[0])
        if len({unit_hash for unit_hash, _ in normalized}) != len(normalized):
            raise ValueError("observation unit_hash values must be unique within a block")
        object.__setattr__(self, "observations", tuple(normalized))

    @property
    def unit_hashes(self) -> tuple[str, ...]:
        return tuple(unit_hash for unit_hash, _ in self.observations)

    @property
    def unit_set_hash(self) -> str:
        return canonical_json_hash({"schema_version": "sequential_unit_set.v1", "unit_hashes": list(self.unit_hashes)})

    @property
    def block_hash(self) -> str:
        return canonical_json_hash(
            {
                "schema_version": "sequential_block.v1",
                "block_id": self.block_id,
                "information_time": self.information_time,
                "snapshot_hash": self.snapshot_hash,
                "manifest_hash": self.manifest_hash,
                "filtration_hash": self.filtration_hash,
                "scope": self.scope,
                "observations": [list(item) for item in self.observations],
            }
        )


@dataclass(frozen=True)
class SequentialState:
    """Complete log-domain state required for deterministic continuation."""

    schema_version: Literal["sequential_state.v1"]
    protocol_hash: str
    look_index: int
    information_time: int
    cumulative_observations: int
    used_block_ids: tuple[str, ...]
    used_block_hashes: tuple[str, ...]
    used_unit_hashes: tuple[str, ...]
    support_component_log_capitals: tuple[float, ...]
    contradiction_component_log_capitals: tuple[float, ...]
    support_log_evidence: float
    contradiction_log_evidence: float
    status: SequentialStatus
    stop_reason: StopReason
    stopped: bool

    def __post_init__(self) -> None:
        for name in (
            "used_block_ids",
            "used_block_hashes",
            "used_unit_hashes",
            "support_component_log_capitals",
            "contradiction_component_log_capitals",
        ):
            value = getattr(self, name)
            if isinstance(value, (str, bytes)):
                raise ValueError(f"{name} must be a sequence")
            object.__setattr__(self, name, tuple(value))
        if self.schema_version != "sequential_state.v1":
            raise ValueError("unsupported sequential state schema")
        _require_digest(self.protocol_hash, name="protocol_hash")
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0
            for value in (self.look_index, self.information_time, self.cumulative_observations)
        ):
            raise ValueError("sequential state counters must be non-negative integers")
        if self.look_index > _MAX_LOOKS or self.cumulative_observations > _MAX_TOTAL_OBSERVATIONS:
            raise ValueError("sequential state exceeds resource limits")
        if len(self.used_block_ids) != self.look_index or len(self.used_block_hashes) != self.look_index:
            raise ValueError("sequential state block history does not match look_index")
        if len(set(self.used_block_ids)) != len(self.used_block_ids) or any(not value for value in self.used_block_ids):
            raise ValueError("sequential state block IDs must be non-empty and unique")
        for value in self.used_block_hashes:
            _require_digest(value, name="used block hash")
        for value in self.used_unit_hashes:
            _require_digest(value, name="used unit hash")
        if len(set(self.used_block_hashes)) != len(self.used_block_hashes) or len(set(self.used_unit_hashes)) != len(
            self.used_unit_hashes
        ):
            raise ValueError("sequential state cannot contain duplicate block or unit hashes")
        if self.used_unit_hashes != tuple(sorted(self.used_unit_hashes)):
            raise ValueError("sequential state unit hashes must be canonically sorted")
        if len(self.used_unit_hashes) > self.cumulative_observations:
            raise ValueError("sequential state unit history exceeds cumulative observations")
        if not self.support_component_log_capitals or len(self.support_component_log_capitals) != len(
            self.contradiction_component_log_capitals
        ):
            raise ValueError("sequential channel component states must be non-empty and aligned")
        numerical = (
            *self.support_component_log_capitals,
            *self.contradiction_component_log_capitals,
            self.support_log_evidence,
            self.contradiction_log_evidence,
        )
        if any(not math.isfinite(value) for value in numerical):
            raise ValueError("sequential state evidence must remain finite in the log domain")
        expected_reason = {
            "continue": "NONE",
            "support_boundary_crossed": "SUPPORT_BOUNDARY",
            "contradiction_boundary_crossed": "CONTRADICTION_BOUNDARY",
            "max_looks_reached": "MAX_LOOKS",
        }.get(self.status)
        if expected_reason is None or self.stop_reason != expected_reason:
            raise ValueError("sequential state status and stop_reason are inconsistent")
        if self.stopped != (self.status != "continue"):
            raise ValueError("sequential state stopped marker is inconsistent")

    @classmethod
    def initial(cls, protocol: SequentialProtocol) -> "SequentialState":
        zeroes = tuple(0.0 for _ in protocol.lambda_grid)
        return cls(
            "sequential_state.v1",
            protocol.protocol_hash,
            0,
            0,
            0,
            (),
            (),
            (),
            zeroes,
            zeroes,
            0.0,
            0.0,
            "continue",
            "NONE",
            False,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "protocol_hash": self.protocol_hash,
            "look_index": self.look_index,
            "information_time": self.information_time,
            "cumulative_observations": self.cumulative_observations,
            "used_block_ids": list(self.used_block_ids),
            "used_block_hashes": list(self.used_block_hashes),
            "used_unit_hashes": list(self.used_unit_hashes),
            "support_component_log_capitals": list(self.support_component_log_capitals),
            "contradiction_component_log_capitals": list(self.contradiction_component_log_capitals),
            "support_log_evidence": self.support_log_evidence,
            "contradiction_log_evidence": self.contradiction_log_evidence,
            "status": self.status,
            "stop_reason": self.stop_reason,
            "stopped": self.stopped,
        }

    @property
    def state_hash(self) -> str:
        return canonical_json_hash(self.to_dict())


@dataclass(frozen=True)
class SequentialLook:
    """Persistable audit record for one sequential update."""

    schema_version: Literal["sequential_look.v1"]
    protocol_hash: str
    previous_state_hash: str
    state_hash: str
    look_index: int
    information_time: int
    block_id: str
    block_hash: str
    unit_set_hash: str
    unit_hashes: tuple[str, ...]
    observation_count: int
    cumulative_observations: int
    support_component_log_capitals: tuple[float, ...]
    contradiction_component_log_capitals: tuple[float, ...]
    support_log_evidence: float
    contradiction_log_evidence: float
    support_e_value: float
    contradiction_e_value: float
    support_boundary: float
    contradiction_boundary: float
    status: SequentialStatus
    stop_reason: StopReason

    def __post_init__(self) -> None:
        object.__setattr__(self, "unit_hashes", tuple(self.unit_hashes))
        object.__setattr__(self, "support_component_log_capitals", tuple(self.support_component_log_capitals))
        object.__setattr__(
            self,
            "contradiction_component_log_capitals",
            tuple(self.contradiction_component_log_capitals),
        )
        if self.schema_version != "sequential_look.v1":
            raise ValueError("unsupported sequential look schema")
        for name in ("protocol_hash", "previous_state_hash", "state_hash", "block_hash", "unit_set_hash"):
            _require_digest(getattr(self, name), name=name)
        for unit_hash in self.unit_hashes:
            _require_digest(unit_hash, name="unit_hash")
        if not self.unit_hashes or self.unit_hashes != tuple(sorted(set(self.unit_hashes))):
            raise ValueError("unit_hashes must be non-empty, sorted, and unique")
        if not isinstance(self.look_index, int) or isinstance(self.look_index, bool) or self.look_index < 1:
            raise ValueError("look_index must be a positive integer")
        if not isinstance(self.information_time, int) or isinstance(self.information_time, bool) or self.information_time < 1:
            raise ValueError("information_time must be a positive integer")
        if not isinstance(self.block_id, str) or not self.block_id.strip():
            raise ValueError("block_id is required")
        if not isinstance(self.observation_count, int) or not 1 <= self.observation_count <= _MAX_BLOCK_SIZE:
            raise ValueError("observation_count is outside resource limits")
        if self.observation_count != len(self.unit_hashes):
            raise ValueError("observation_count must match the persisted unit hashes")
        if not isinstance(self.cumulative_observations, int) or not self.observation_count <= self.cumulative_observations <= _MAX_TOTAL_OBSERVATIONS:
            raise ValueError("cumulative_observations is outside resource limits")
        numerical = (
            *self.support_component_log_capitals,
            *self.contradiction_component_log_capitals,
            self.support_log_evidence,
            self.contradiction_log_evidence,
            self.support_e_value,
            self.contradiction_e_value,
            self.support_boundary,
            self.contradiction_boundary,
        )
        if any(not math.isfinite(value) for value in numerical):
            raise ValueError("sequential look evidence and boundaries must be finite")
        if not self.support_component_log_capitals or len(self.support_component_log_capitals) != len(
            self.contradiction_component_log_capitals
        ):
            raise ValueError("sequential look channel component states must be non-empty and aligned")
        if self.support_e_value < 0 or self.contradiction_e_value < 0 or self.support_boundary <= 1 or self.contradiction_boundary <= 1:
            raise ValueError("sequential e-values or boundaries are invalid")
        expected_reason = {
            "continue": "NONE",
            "support_boundary_crossed": "SUPPORT_BOUNDARY",
            "contradiction_boundary_crossed": "CONTRADICTION_BOUNDARY",
            "max_looks_reached": "MAX_LOOKS",
        }.get(self.status)
        if expected_reason is None or self.stop_reason != expected_reason:
            raise ValueError("sequential look status and stop_reason are inconsistent")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "protocol_hash": self.protocol_hash,
            "previous_state_hash": self.previous_state_hash,
            "state_hash": self.state_hash,
            "look_index": self.look_index,
            "information_time": self.information_time,
            "block_id": self.block_id,
            "block_hash": self.block_hash,
            "unit_set_hash": self.unit_set_hash,
            "unit_hashes": list(self.unit_hashes),
            "observation_count": self.observation_count,
            "cumulative_observations": self.cumulative_observations,
            "support_component_log_capitals": list(self.support_component_log_capitals),
            "contradiction_component_log_capitals": list(self.contradiction_component_log_capitals),
            "support_log_evidence": self.support_log_evidence,
            "contradiction_log_evidence": self.contradiction_log_evidence,
            "support_e_value": self.support_e_value,
            "contradiction_e_value": self.contradiction_e_value,
            "support_boundary": self.support_boundary,
            "contradiction_boundary": self.contradiction_boundary,
            "status": self.status,
            "stop_reason": self.stop_reason,
        }

    @property
    def look_hash(self) -> str:
        return canonical_json_hash(self.to_dict())

    @property
    def incremental_information(self) -> int:
        return self.observation_count

    @property
    def cumulative_support_log_e(self) -> float:
        return self.support_log_evidence

    @property
    def cumulative_contradiction_log_e(self) -> float:
        return self.contradiction_log_evidence


class SequentialExecutor:
    """Feature-gated executor for the one approved v1 e-process."""

    def __init__(self, *, flags: ResolvedAGSFlags) -> None:
        if not flags.enabled("VIBE_TRADING_FALSIFICATION_CONTRACT"):
            raise RuntimeError("sequential falsification capability is disabled")

    @staticmethod
    def initial_state(protocol: SequentialProtocol) -> SequentialState:
        if not isinstance(protocol, SequentialProtocol):
            raise TypeError("SequentialExecutor requires a SequentialProtocol")
        return SequentialState.initial(protocol)

    def advance(
        self,
        protocol: SequentialProtocol,
        state: SequentialState,
        block: SequentialBlock,
        *,
        p_value: float | None = None,
        raw_p_value: float | None = None,
        e_value: float | None = None,
        stopping_boundary: float | None = None,
        stop: bool | None = None,
    ) -> tuple[SequentialState, SequentialLook]:
        """Consume exactly one unobserved block and return its immutable look.

        Explicit evidence/stopping keywords exist only to fail with a clear
        classification when a caller tries to reuse a fixed-horizon or
        caller-judged interface.
        """

        if any(value is not None for value in (p_value, raw_p_value, e_value, stopping_boundary, stop)):
            raise ValueError("sequential looks reject caller-supplied p/e-values, boundaries, and stopping decisions")
        self._validate_continuation(protocol, state, block)
        values = tuple(value for _, value in block.observations)
        if any(value < protocol.lower_bound or value > protocol.upper_bound for value in values):
            raise ValueError("sequential observation is outside the frozen bounds")
        mean = math.fsum(values) / len(values)
        orientation = 1.0 if protocol.expected_direction == "positive" else -1.0
        oriented_lower, oriented_upper = sorted((orientation * protocol.lower_bound, orientation * protocol.upper_bound))
        support_z = self._scaled_increment(orientation * mean, oriented_lower, oriented_upper, protocol.sesoi)
        contradiction_z = self._scaled_increment(-orientation * mean, -oriented_upper, -oriented_lower, protocol.sesoi)
        support_logs = self._update_components(state.support_component_log_capitals, protocol.lambda_grid, support_z)
        contradiction_logs = self._update_components(
            state.contradiction_component_log_capitals, protocol.lambda_grid, contradiction_z
        )
        support_log_evidence = _mixture_log_evidence(support_logs, protocol.mixture_weights)
        contradiction_log_evidence = _mixture_log_evidence(contradiction_logs, protocol.mixture_weights)
        support_crossed = support_log_evidence >= -math.log(protocol.support_alpha)
        contradiction_crossed = contradiction_log_evidence >= -math.log(protocol.contradiction_alpha)
        next_index = state.look_index + 1
        if contradiction_crossed:
            status: SequentialStatus = "contradiction_boundary_crossed"
            reason: StopReason = "CONTRADICTION_BOUNDARY"
            stopped = True
        elif support_crossed:
            status = "support_boundary_crossed"
            reason = "SUPPORT_BOUNDARY"
            stopped = True
        elif next_index == protocol.maximum_looks:
            status = "max_looks_reached"
            reason = "MAX_LOOKS"
            stopped = True
        else:
            status = "continue"
            reason = "NONE"
            stopped = False
        previous_state_hash = state.state_hash
        new_state = SequentialState(
            "sequential_state.v1",
            protocol.protocol_hash,
            next_index,
            block.information_time,
            state.cumulative_observations + len(block.observations),
            state.used_block_ids + (block.block_id,),
            state.used_block_hashes + (block.block_hash,),
            tuple(sorted((*state.used_unit_hashes, *block.unit_hashes))),
            support_logs,
            contradiction_logs,
            support_log_evidence,
            contradiction_log_evidence,
            status,
            reason,
            stopped,
        )
        look = SequentialLook(
            "sequential_look.v1",
            protocol.protocol_hash,
            previous_state_hash,
            new_state.state_hash,
            next_index,
            block.information_time,
            block.block_id,
            block.block_hash,
            block.unit_set_hash,
            block.unit_hashes,
            len(block.observations),
            new_state.cumulative_observations,
            support_logs,
            contradiction_logs,
            support_log_evidence,
            contradiction_log_evidence,
            _reported_e_value(support_log_evidence),
            _reported_e_value(contradiction_log_evidence),
            protocol.support_boundary,
            protocol.contradiction_boundary,
            status,
            reason,
        )
        return new_state, look

    def replay(
        self,
        protocol: SequentialProtocol,
        blocks: Sequence[SequentialBlock],
        *,
        expected_looks: Sequence[SequentialLook] | None = None,
    ) -> tuple[SequentialState, tuple[SequentialLook, ...]]:
        """Recompute a sequence and optionally verify every persisted look hash."""

        state = self.initial_state(protocol)
        looks: list[SequentialLook] = []
        for block in blocks:
            state, look = self.advance(protocol, state, block)
            looks.append(look)
        result = tuple(looks)
        if expected_looks is not None:
            if tuple(look.look_hash for look in result) != tuple(look.look_hash for look in expected_looks):
                raise ValueError("sequential replay does not match persisted looks")
        return state, result

    @staticmethod
    def _scaled_increment(mean: float, lower: float, upper: float, null_boundary: float) -> float:
        scale = max(abs(upper - null_boundary), abs(lower - null_boundary))
        if not math.isfinite(scale) or scale <= 0:
            raise ValueError("frozen bounds do not define a valid sequential null")
        increment = (mean - null_boundary) / scale
        # A tiny floating error at a declared bound must not produce a negative
        # betting factor, but a material violation is an implementation error.
        if increment < -1.0 - 1e-12 or increment > 1.0 + 1e-12:
            raise ValueError("scaled sequential increment is outside [-1, 1]")
        return min(1.0, max(-1.0, increment))

    @staticmethod
    def _update_components(
        previous_logs: Sequence[float], lambdas: Sequence[float], increment: float
    ) -> tuple[float, ...]:
        return tuple(
            previous + math.log1p(bet * increment)
            for previous, bet in zip(previous_logs, lambdas, strict=True)
        )

    @staticmethod
    def _validate_continuation(
        protocol: SequentialProtocol, state: SequentialState, block: SequentialBlock
    ) -> None:
        if not isinstance(protocol, SequentialProtocol):
            raise TypeError("SequentialExecutor requires a SequentialProtocol")
        if not isinstance(state, SequentialState) or not isinstance(block, SequentialBlock):
            raise TypeError("SequentialExecutor requires typed state and block inputs")
        if state.protocol_hash != protocol.protocol_hash:
            raise ValueError("state belongs to a different frozen sequential protocol")
        if state.stopped:
            raise ValueError("no sequential look may be appended after the frozen stopping rule fires")
        if state.look_index >= protocol.maximum_looks:
            raise ValueError("maximum_looks has already been reached")
        if len(state.support_component_log_capitals) != len(protocol.lambda_grid) or len(
            state.contradiction_component_log_capitals
        ) != len(protocol.lambda_grid):
            raise ValueError("sequential component state does not match the frozen mixture")
        if (
            state.information_time != state.cumulative_observations
            or len(state.used_unit_hashes) != state.cumulative_observations
            or state.used_block_ids != protocol.block_schedule[: state.look_index]
        ):
            raise ValueError("sequential state history does not match the frozen protocol")
        expected_support = _mixture_log_evidence(
            state.support_component_log_capitals, protocol.mixture_weights
        )
        expected_contradiction = _mixture_log_evidence(
            state.contradiction_component_log_capitals, protocol.mixture_weights
        )
        if not math.isclose(
            state.support_log_evidence, expected_support, rel_tol=0.0, abs_tol=1e-12
        ) or not math.isclose(
            state.contradiction_log_evidence,
            expected_contradiction,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("sequential state cumulative evidence is internally inconsistent")
        if (
            state.support_log_evidence >= protocol.support_log_boundary
            or state.contradiction_log_evidence >= protocol.contradiction_log_boundary
        ):
            raise ValueError("sequential continuation state already crossed a stopping boundary")
        if block.scope != protocol.scope:
            raise ValueError("block scope does not match the validation-only protocol")
        if block.snapshot_hash != protocol.snapshot_hash or block.manifest_hash != protocol.manifest_hash:
            raise ValueError("block snapshot or manifest differs from the frozen protocol")
        if block.filtration_hash != protocol.filtration_hash:
            raise ValueError("block filtration differs from the frozen protocol")
        if block.block_id in state.used_block_ids or block.block_hash in state.used_block_hashes:
            raise ValueError("sequential look cannot reuse an observed block")
        if set(block.unit_hashes).intersection(state.used_unit_hashes):
            raise ValueError("sequential look cannot reuse an observed unit")
        expected_block_id = protocol.block_schedule[state.look_index]
        if block.block_id != expected_block_id:
            raise ValueError("sequential block is not the next pre-registered block")
        expected_information_time = state.cumulative_observations + len(block.observations)
        if block.information_time != expected_information_time:
            raise ValueError("sequential information_time must equal cumulative unobserved observations")
        if len(block.observations) < protocol.minimum_block_size:
            raise ValueError("sequential block is below the frozen minimum block size")
        if state.cumulative_observations + len(block.observations) > _MAX_TOTAL_OBSERVATIONS:
            raise ValueError("sequential protocol exceeds the cumulative observation limit")


__all__ = [
    "APPROVED_METHOD",
    "APPROVED_STOPPING_RULE",
    "SequentialBlock",
    "SequentialContract",
    "SequentialExecutor",
    "SequentialLook",
    "SequentialProtocol",
    "SequentialState",
    "SequentialStatus",
    "StopReason",
    "UnsupportedSequentialMethod",
]
