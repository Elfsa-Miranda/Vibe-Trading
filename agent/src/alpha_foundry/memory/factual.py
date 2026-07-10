"""Read-only factual memory derived from DAG and typed event references."""

from __future__ import annotations

from dataclasses import dataclass

from src.alpha_foundry.dag.model import FactorDAGProjection


@dataclass(frozen=True)
class FactualMemoryView:
    dag: FactorDAGProjection

    def factor_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self.dag.factor_nodes))

    def definition_event_hash(self, factor_spec_id: str) -> str:
        return self.dag.factor_nodes[factor_spec_id].definition_event_hash


__all__ = ["FactualMemoryView"]
