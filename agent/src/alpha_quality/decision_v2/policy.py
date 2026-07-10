"""Frozen deterministic Decision v2 policy."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from src.research_ledger.hash_utils import canonical_json_hash


@dataclass(frozen=True)
class DecisionV2Policy:
    schema_version: Literal["decision_v2_policy.v1"]
    policy_version: str
    require_snapshot: bool = True
    require_execution: bool = True
    require_mechanism: bool = True
    require_complement: bool = True
    rank_ic_score_scale: float = 0.10

    def __post_init__(self) -> None:
        if self.schema_version != "decision_v2_policy.v1":
            raise ValueError("unsupported Decision v2 policy schema")
        if not self.policy_version or len(self.policy_version) > 128:
            raise ValueError("policy_version must be bounded non-empty text")
        if not math.isfinite(self.rank_ic_score_scale) or self.rank_ic_score_scale <= 0.0:
            raise ValueError("rank_ic_score_scale must be finite and positive")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "policy_version": self.policy_version,
            "require_snapshot": self.require_snapshot,
            "require_execution": self.require_execution,
            "require_mechanism": self.require_mechanism,
            "require_complement": self.require_complement,
            "rank_ic_score_scale": self.rank_ic_score_scale,
        }

    @property
    def policy_hash(self) -> str:
        return canonical_json_hash(self.to_dict())


__all__ = ["DecisionV2Policy"]
