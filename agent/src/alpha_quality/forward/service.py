"""Append-only v2 forward plan and observation service."""

from __future__ import annotations

from pathlib import Path

from src.alpha_quality.flags import ResolvedAGSFlags
from src.alpha_quality.forward.model import ForwardObservationV2, FrozenForwardPlan
from src.research_ledger.events import EventDraft, ResearchEventStore
from src.research_ledger.hash_utils import canonical_json, utc_now_iso


class ForwardMonitoringService:
    def __init__(self, *, store: ResearchEventStore, flags: ResolvedAGSFlags) -> None:
        if not flags.enabled("VIBE_TRADING_FORWARD_TRACKING"):
            raise RuntimeError("forward monitoring capability is disabled")
        self.store = store

    def record_plan(self, plan: FrozenForwardPlan, *, run_id: str):
        final_events = [
            event
            for event in self.store.query_events(event_type="FinalTestArtifactRecorded")
            if event.payload["artifact_hash"] == plan.final_test_artifact_hash
        ]
        if not final_events or (
            final_events[-1].payload["factor_spec_id"] != plan.factor_spec_id
            or not final_events[-1].payload["quality_passed"]
            or final_events[-1].payload["contaminated"]
            or any(
                final_events[-1].payload[field] != getattr(plan, field)
                for field in (
                    "definition_hash",
                    "transform_pipeline_hash",
                    "cost_model_hash",
                    "regime_config_hash",
                    "policy_hash",
                )
            )
        ):
            raise ValueError("forward plan requires qualified uncontaminated final evidence")
        reference = self._write_artifact("forward_plans", plan.plan_hash, plan.to_dict())
        return self.store.append_event(
            EventDraft(
                event_type="ForwardPlanV2Recorded",
                entity_id=plan.plan_id,
                run_id=run_id,
                payload_schema_version="forward_plan_recorded.v2",
                idempotency_key="forward-plan-v2:" + plan.plan_hash,
                payload={
                    "plan_schema_version": plan.schema_version,
                    "plan_id": plan.plan_id,
                    "factor_spec_id": plan.factor_spec_id,
                    "final_test_artifact_hash": plan.final_test_artifact_hash,
                    "definition_hash": plan.definition_hash,
                    "transform_pipeline_hash": plan.transform_pipeline_hash,
                    "cost_model_hash": plan.cost_model_hash,
                    "regime_config_hash": plan.regime_config_hash,
                    "policy_hash": plan.policy_hash,
                    "expected_horizon": plan.expected_horizon,
                    "minimum_effective_observations": plan.minimum_effective_observations,
                    "minimum_rank_ic": plan.minimum_rank_ic,
                    "maximum_drawdown": plan.maximum_drawdown,
                    "kill_rules_hash": plan.kill_rules_hash,
                    "created_at": plan.created_at,
                    "plan_hash": plan.plan_hash,
                    "artifact_refs": [reference],
                },
            )
        )

    def append_observation(
        self,
        plan: FrozenForwardPlan,
        *,
        period_start: str,
        period_end: str,
        effective_observations: int,
        rank_ic: float,
        net_return: float,
        drawdown: float,
        run_id: str,
    ) -> ForwardObservationV2:
        registered = self.store.query_events(
            event_type="ForwardPlanV2Recorded", entity_id=plan.plan_id
        )
        if not registered or registered[-1].payload["plan_hash"] != plan.plan_hash:
            raise ValueError("forward observation requires its registered frozen plan")
        prior = [
            event
            for event in self.store.query_events(event_type="ForwardObservationV2Recorded")
            if event.payload["plan_id"] == plan.plan_id
        ]
        if prior and period_start <= str(prior[-1].payload["period_end"]):
            raise ValueError("forward observations must append after the prior period")
        previous_hash = None if not prior else str(prior[-1].payload["observation_hash"])
        observation = ForwardObservationV2.create(
            plan=plan,
            period_start=period_start,
            period_end=period_end,
            effective_observations=effective_observations,
            rank_ic=rank_ic,
            net_return=net_return,
            drawdown=drawdown,
            previous_observation_hash=previous_hash,
            observed_at=utc_now_iso(),
        )
        reference = self._write_artifact(
            "forward_observations", observation.observation_hash, observation.to_dict()
        )
        self.store.append_event(
            EventDraft(
                event_type="ForwardObservationV2Recorded",
                entity_id=observation.observation_id,
                run_id=run_id,
                payload_schema_version="forward_observation_recorded.v2",
                idempotency_key="forward-observation-v2:" + observation.observation_hash,
                payload={
                    "observation_schema_version": observation.schema_version,
                    "observation_id": observation.observation_id,
                    "plan_id": observation.plan_id,
                    "plan_hash": observation.plan_hash,
                    "period_start": observation.period_start,
                    "period_end": observation.period_end,
                    "effective_observations": observation.effective_observations,
                    "rank_ic": observation.rank_ic,
                    "net_return": observation.net_return,
                    "drawdown": observation.drawdown,
                    "previous_observation_hash": observation.previous_observation_hash,
                    "observed_at": observation.observed_at,
                    "observation_hash": observation.observation_hash,
                    "artifact_refs": [reference],
                },
            )
        )
        return observation

    def _write_artifact(
        self, directory: str, content_hash: str, payload: dict[str, object]
    ) -> dict[str, str]:
        relative = Path(directory) / (content_hash.removeprefix("sha256:") + ".json")
        path = self.store.artifact_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            temporary = path.with_suffix(".tmp")
            temporary.write_text(canonical_json(payload), encoding="utf-8")
            temporary.replace(path)
        return {
            "relative_path": relative.as_posix(),
            "artifact_hash": self.store.hash_artifact(path),
            "media_type": "application/json",
        }


__all__ = ["ForwardMonitoringService"]
