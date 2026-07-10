"""Immutable derived models for factual and episodic process memory."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


_EPISODIC_PROJECTION_AUTHORITY = object()


@dataclass(frozen=True)
class ProcessMemoryObservation:
    parent_context_hash: str
    parent_factor_spec_id: str
    child_factor_spec_id: str
    derivation_event_hash: str
    evaluation_event_hash: str
    scorecard_hash: str
    ast_diff_hash: str
    motif_version: str
    motif: str
    base_expected_utility: float
    observed_validation_utility: float | None
    residual: float | None
    terminal_status: str
    failure_codes: tuple[str, ...]
    regime_config_hash: str | None
    data_snapshot_hash: str
    eligible_event_watermark: str
    run_group_id: str
    policy_hash: str
    available_at: str


@dataclass(frozen=True)
class ProcessPosterior:
    parent_context_hash: str
    motif: str
    effective_count: int
    observation_count: int
    mean_residual: float
    residual_standard_error: float | None
    confidence: float
    positive_adjustment: float
    hard_veto: bool


@dataclass(frozen=True)
class EpisodicProjection:
    schema_version: Literal["episodic_process_projection.v2"]
    source_watermark_event_hash: str | None
    observations: tuple[ProcessMemoryObservation, ...]
    posteriors: tuple[ProcessPosterior, ...]
    projection_hash: str
    _authority: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._authority is not _EPISODIC_PROJECTION_AUTHORITY:
            raise TypeError("episodic projection must be built by EpisodicProjector")


def authorized_episodic_projection(**values: object) -> EpisodicProjection:
    return EpisodicProjection(**values, _authority=_EPISODIC_PROJECTION_AUTHORITY)  # type: ignore[arg-type]


def is_authorized_episodic_projection(value: EpisodicProjection) -> bool:
    return value._authority is _EPISODIC_PROJECTION_AUTHORITY


__all__ = [
    "EpisodicProjection", "ProcessMemoryObservation", "ProcessPosterior",
    "authorized_episodic_projection", "is_authorized_episodic_projection",
]
