"""Forward-only projection and monitoring view; never a discovery input."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from src.alpha_quality.forward.model import (
    ForwardObservationV2,
    FrozenForwardPlan,
    MonitoringEvidenceView,
)
from src.research_ledger.events import ResearchEventEnvelope
from src.research_ledger.hash_utils import canonical_json_hash


@dataclass(frozen=True)
class ForwardProjection:
    plans: Mapping[str, ResearchEventEnvelope]
    observations: Mapping[str, tuple[ResearchEventEnvelope, ...]]
    projection_hash: str


class ForwardProjector:
    def project(self, events: Iterable[ResearchEventEnvelope]) -> ForwardProjection:
        plans: dict[str, ResearchEventEnvelope] = {}
        observations: dict[str, list[ResearchEventEnvelope]] = {}
        source_hashes: list[str] = []
        for event in events:
            if event.event_type == "ForwardPlanV2Recorded":
                plans[str(event.payload["plan_id"])] = event
                source_hashes.append(event.event_hash)
            elif event.event_type == "ForwardObservationV2Recorded":
                observations.setdefault(str(event.payload["plan_id"]), []).append(event)
                source_hashes.append(event.event_hash)
        frozen_observations = {
            plan_id: tuple(items) for plan_id, items in sorted(observations.items())
        }
        return ForwardProjection(
            plans=plans,
            observations=frozen_observations,
            projection_hash=canonical_json_hash(
                {
                    "schema_version": "forward_projection.v2",
                    "source_event_hashes": source_hashes,
                }
            ),
        )

    @staticmethod
    def monitoring_view(
        plan: FrozenForwardPlan,
        observations: tuple[ForwardObservationV2, ...],
        *,
        claim_success: bool = False,
    ) -> MonitoringEvidenceView:
        previous_hash: str | None = None
        previous_end: str | None = None
        for observation in observations:
            if observation.plan_id != plan.plan_id or observation.plan_hash != plan.plan_hash:
                raise ValueError("monitoring observation does not belong to frozen plan")
            if observation.previous_observation_hash != previous_hash:
                raise ValueError("monitoring observations do not form the frozen hash chain")
            if previous_end is not None and observation.period_start <= previous_end:
                raise ValueError("monitoring observations are out of period order")
            previous_hash = observation.observation_hash
            previous_end = observation.period_end
        total = sum(item.effective_observations for item in observations)
        kill_triggered = any(
            item.rank_ic < plan.minimum_rank_ic or item.drawdown > plan.maximum_drawdown
            for item in observations
        )
        if claim_success and total < plan.minimum_effective_observations:
            raise ValueError("forward success is forbidden before minimum effective observations")
        status = (
            "kill_triggered"
            if kill_triggered
            else "insufficient"
            if total < plan.minimum_effective_observations
            else "monitoring"
        )
        statement = (
            "MINIMUM_OBSERVATIONS_REACHED_MONITORING_ONLY"
            if claim_success and total >= plan.minimum_effective_observations
            else None
        )
        limitations = {
            "FORWARD_MONITORING_ONLY",
            "NO_AUTOMATIC_DISCOVERY_OR_PROMOTION_UPDATE",
        }
        if total < plan.minimum_effective_observations:
            limitations.add("MINIMUM_EFFECTIVE_OBSERVATIONS_NOT_REACHED")
        hashes = tuple(item.observation_hash for item in observations)
        content = {
            "schema_version": "monitoring_evidence_view.v1",
            "scope": "monitoring",
            "plan_id": plan.plan_id,
            "plan_hash": plan.plan_hash,
            "factor_spec_id": plan.factor_spec_id,
            "effective_observations": total,
            "status": status,
            "observation_hashes": list(hashes),
            "success_statement": statement,
            "limitations": sorted(limitations),
        }
        return MonitoringEvidenceView(
            schema_version="monitoring_evidence_view.v1",
            scope="monitoring",
            plan_id=plan.plan_id,
            plan_hash=plan.plan_hash,
            factor_spec_id=plan.factor_spec_id,
            effective_observations=total,
            status=status,  # type: ignore[arg-type]
            observation_hashes=hashes,
            success_statement=statement,
            limitations=tuple(sorted(limitations)),
            view_hash=canonical_json_hash(content),
        )


__all__ = ["ForwardProjection", "ForwardProjector"]
