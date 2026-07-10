"""Terminal train/valid factual evidence separated from raw audit lineage."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Iterable, Mapping

from src.alpha_foundry.dag.model import FactorDAGProjection
from src.research_ledger.events import ResearchEventEnvelope


_FACTUAL_VIEW_AUTHORITY = object()


@dataclass(frozen=True)
class DiscoveryFactorEvidence:
    factor_spec_id: str
    definition_event_hash: str
    evaluation_event_hash: str
    terminal_event_hash: str
    scorecard_hash: str
    data_scope: str


@dataclass(frozen=True)
class FactualMemoryView:
    dag: FactorDAGProjection
    evidence_by_factor_spec_id: Mapping[str, DiscoveryFactorEvidence]
    _authority: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._authority is not _FACTUAL_VIEW_AUTHORITY:
            raise TypeError("factual memory must be built from terminal discovery events")
        object.__setattr__(
            self,
            "evidence_by_factor_spec_id",
            MappingProxyType(dict(self.evidence_by_factor_spec_id)),
        )

    @classmethod
    def from_terminal_discovery_events(
        cls,
        dag: FactorDAGProjection,
        events: Iterable[ResearchEventEnvelope],
    ) -> "FactualMemoryView":
        ordered = list(events)
        evaluations = {
            event.event_hash: event
            for event in ordered
            if event.event_type == "EvaluationRecorded"
            and event.payload["data_scope"] in {"valid", "train_valid"}
        }
        eligible: dict[str, DiscoveryFactorEvidence] = {}
        for terminal in ordered:
            if terminal.event_type != "TrialTerminated" or terminal.payload["status"] not in {"success", "reject"}:
                continue
            evaluation_hash = terminal.payload["evaluation_event_hash"]
            if evaluation_hash is None:
                # Rejected trials may cite their evaluation through hardened
                # process outcomes rather than the v1 terminal payload.
                outcomes = [
                    event for event in ordered
                    if event.event_type == "ProcessOutcomeRecordedV2"
                    and event.payload["terminal_event_hash"] == terminal.event_hash
                ]
                if len(outcomes) != 1:
                    continue
                evaluation_hash = outcomes[0].payload["evaluation_event_hash"]
            evaluation = evaluations.get(str(evaluation_hash))
            if evaluation is None or evaluation.payload["trial_id"] != terminal.payload["trial_id"]:
                continue
            factor_id = str(evaluation.payload["factor_spec_id"])
            node = dag.factor_nodes.get(factor_id)
            if node is None:
                continue
            eligible[factor_id] = DiscoveryFactorEvidence(
                factor_spec_id=factor_id,
                definition_event_hash=node.definition_event_hash,
                evaluation_event_hash=evaluation.event_hash,
                terminal_event_hash=terminal.event_hash,
                scorecard_hash=str(evaluation.payload["scorecard_hash"]),
                data_scope=str(evaluation.payload["data_scope"]),
            )
        return cls(
            dag=dag,
            evidence_by_factor_spec_id=eligible,
            _authority=_FACTUAL_VIEW_AUTHORITY,
        )

    def is_authorized(self) -> bool:
        return self._authority is _FACTUAL_VIEW_AUTHORITY

    def factor_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self.evidence_by_factor_spec_id))

    def definition_event_hash(self, factor_spec_id: str) -> str:
        return self.evidence_by_factor_spec_id[factor_spec_id].definition_event_hash


__all__ = ["DiscoveryFactorEvidence", "FactualMemoryView"]
