"""Versioned bounded topology/memory fusion policy."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from src.research_ledger.hash_utils import canonical_json_hash


@dataclass(frozen=True)
class RetrieverPolicy:
    policy_version: str = "topology_shadow_policy.v2"
    epsilon: float = 1e-9
    memory_weight: float = 0.5
    residual_clip: float = 0.25
    veto_exploration_probability: float = 0.05
    softmax_temperature: float = 1.0
    maximum_candidate_budget: int = 10_000

    def __post_init__(self) -> None:
        if self.policy_version != "topology_shadow_policy.v2":
            raise ValueError("unsupported topology retriever policy")
        if not math.isfinite(self.epsilon) or not 0.0 < self.epsilon <= 1e-3:
            raise ValueError("retriever epsilon is out of bounds")
        if not math.isfinite(self.memory_weight) or not 0.0 <= self.memory_weight <= 1.0:
            raise ValueError("memory weight must be in [0, 1]")
        if not math.isfinite(self.residual_clip) or not 0.0 < self.residual_clip <= 1.0:
            raise ValueError("residual clip must be in (0, 1]")
        if not 0.0 <= self.veto_exploration_probability <= 0.25:
            raise ValueError("veto exploration probability must be in [0, .25]")
        if not math.isfinite(self.softmax_temperature) or not 0.0 < self.softmax_temperature <= 10.0:
            raise ValueError("softmax temperature must be in (0, 10]")
        if not 1 <= self.maximum_candidate_budget <= 100_000:
            raise ValueError("maximum candidate budget is out of bounds")

    @property
    def policy_hash(self) -> str:
        return canonical_json_hash(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_version": self.policy_version,
            "epsilon": self.epsilon,
            "memory_weight": self.memory_weight,
            "residual_clip": self.residual_clip,
            "veto_exploration_probability": self.veto_exploration_probability,
            "softmax_temperature": self.softmax_temperature,
            "maximum_candidate_budget": self.maximum_candidate_budget,
        }


__all__ = ["RetrieverPolicy"]
