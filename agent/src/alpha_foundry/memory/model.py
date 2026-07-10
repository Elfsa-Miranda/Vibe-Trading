"""Immutable derived models for factual and episodic process memory."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ProcessMemoryObservation:
    parent_context_hash: str
    parent_factor_spec_id: str
    child_factor_spec_id: str
    derivation_event_hash: str
    ast_diff_hash: str
    motif_version: str
    motif: str
    base_expected_utility: float
    observed_validation_utility: float | None
    residual: float | None
    terminal_status: str
    failure_codes: tuple[str, ...]
    regime_config_hash: str | None
    policy_hash: str
    available_at: str


@dataclass(frozen=True)
class ProcessPosterior:
    parent_context_hash: str
    motif: str
    effective_count: int
    mean_residual: float
    confidence: float
    positive_adjustment: float
    hard_veto: bool


@dataclass(frozen=True)
class EpisodicProjection:
    schema_version: Literal["episodic_process_projection.v1"]
    source_watermark_event_hash: str | None
    observations: tuple[ProcessMemoryObservation, ...]
    posteriors: tuple[ProcessPosterior, ...]
    projection_hash: str


__all__ = ["EpisodicProjection", "ProcessMemoryObservation", "ProcessPosterior"]
