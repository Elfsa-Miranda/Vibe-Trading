"""Typed, discovery-only inputs and outputs for non-influential retrieval."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal

@dataclass(frozen=True)
class DiscoveryEvidenceView:
    source_watermark: str | None
    scope: Literal["discovery"] = "discovery"
    def __post_init__(self):
        if self.scope != "discovery": raise ValueError("retriever accepts discovery evidence only")

@dataclass(frozen=True)
class FactorOutputFeature:
    factor_spec_id: str
    aligned_train_valid_outputs: tuple[float, ...]
    semantic_diversity: float | None
    structural_diversity: float
    child_quality_gain: float | None = None

@dataclass(frozen=True)
class ShadowDecision:
    selected_factor_spec_ids: tuple[str, ...]
    selection_propensity: float
    seed: int
    policy_hash: str
    eligible_event_watermark: str | None
    veto_reason: str | None
    components: tuple[tuple[str, float, tuple[str, ...]], ...]

__all__=["DiscoveryEvidenceView","FactorOutputFeature","ShadowDecision"]
