"""Immutable, derived read model for the event-sourced factor lineage DAG."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, Mapping


class FactorDAGError(ValueError):
    """Raised when event history cannot form an unambiguous lineage DAG."""


@dataclass(frozen=True)
class FactorNode:
    factor_spec_id: str
    expression_id: str
    canonical_ast_hash: str
    grammar_version: str
    grammar_hash: str
    originating_trial_id: str
    definition_event_hash: str


@dataclass(frozen=True)
class RegistryRootNode:
    root_id: str
    snapshot_id: str
    alpha_id: str
    status: Literal["canonical_dsl", "legacy_opaque"]
    expression_id: str | None
    legacy_formula_hash: str
    canonical_formula: str | None
    source_hash: str | None
    source_status: Literal["available", "unavailable"]
    source_reason: str | None
    bootstrap_event_hash: str


@dataclass(frozen=True)
class DerivationEdge:
    child_factor_spec_id: str
    parent_factor_spec_ids: tuple[str, ...]
    trial_terminal_event_hash: str
    derivation_kind: Literal["mutation", "crossover", "manual_registered"]
    event_hash: str


@dataclass(frozen=True)
class SimilarityEvidence:
    """Non-lineage relation deliberately excluded from parent/child traversal."""

    left_factor_spec_id: str
    right_factor_spec_id: str
    evidence_kind: str
    evidence_hash: str


@dataclass(frozen=True)
class FactorDAGProjection:
    schema_version: Literal["factor_dag_projection.v1"]
    source_event_count: int
    source_watermark_event_hash: str | None
    factor_nodes: Mapping[str, FactorNode]
    registry_roots: Mapping[str, RegistryRootNode]
    derivation_edges: tuple[DerivationEdge, ...]
    depth_by_factor_spec_id: Mapping[str, int]
    projection_hash: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "factor_nodes", MappingProxyType(dict(self.factor_nodes)))
        object.__setattr__(self, "registry_roots", MappingProxyType(dict(self.registry_roots)))
        object.__setattr__(self, "depth_by_factor_spec_id", MappingProxyType(dict(self.depth_by_factor_spec_id)))
        object.__setattr__(self, "derivation_edges", tuple(self.derivation_edges))


__all__ = [
    "DerivationEdge",
    "FactorDAGError",
    "FactorDAGProjection",
    "FactorNode",
    "RegistryRootNode",
    "SimilarityEvidence",
]
