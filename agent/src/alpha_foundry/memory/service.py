"""Production entrypoint for pre-generation actions and evaluated process outcomes."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from src.alpha_foundry.dsl.diff import extract_ast_diff
from src.alpha_foundry.dsl.identity import ExpressionIdentity
from src.alpha_quality.flags import ResolvedAGSFlags
from src.research_ledger.events import EventDraft, ResearchEventEnvelope, ResearchEventStore
from src.research_ledger.hash_utils import canonical_json_hash, utc_now_iso


_SCORECARD_MEDIA_TYPE = "application/vnd.vibe.alpha-quality-scorecard+json"


@dataclass(frozen=True)
class ValidationUtilityPolicy:
    """Frozen deterministic mapping from a validation scorecard to utility."""

    schema_version: str = "validation_utility_policy.v1"
    metric: str = "mean_valid_rank_icir"

    def __post_init__(self) -> None:
        if self.schema_version != "validation_utility_policy.v1" or self.metric != "mean_valid_rank_icir":
            raise ValueError("unsupported validation utility policy")

    @property
    def policy_hash(self) -> str:
        return canonical_json_hash(
            {"schema_version": self.schema_version, "metric": self.metric}
        )


class ProcessMemoryService:
    """Write only v2 process evidence that can be independently replayed.

    The older v1 events remain readable audit history but are intentionally not
    emitted here or admitted to the hardened episodic projection.
    """

    def __init__(
        self,
        *,
        store: ResearchEventStore,
        flags: ResolvedAGSFlags,
        utility_policy: ValidationUtilityPolicy | None = None,
    ) -> None:
        required = (
            "VIBE_TRADING_ALPHA_FOUNDRY",
            "VIBE_TRADING_RESEARCH_EVENTS",
            "VIBE_TRADING_FACTOR_DAG",
            "VIBE_TRADING_PROCESS_MEMORY",
        )
        if any(not flags.enabled(name) for name in required):
            raise RuntimeError("process memory capability is disabled")
        self.store = store
        self.utility_policy = utility_policy or ValidationUtilityPolicy()

    def freeze_action(
        self,
        *,
        action_id: str,
        trial_id: str,
        parent_factor_spec_id: str,
        candidate_id: str,
        base_expected_utility: float,
        eligible_event_watermark: str,
        policy_hash: str,
        data_snapshot_hash: str,
        run_group_id: str,
        seed: int,
        candidate_budget: int,
        run_id: str,
        regime_config_hash: str | None = None,
    ) -> ResearchEventEnvelope:
        existing = self.store.query_events(
            event_type="ProcessActionFrozenV2", entity_id=action_id
        )
        if existing:
            self._require_retry_matches(
                existing[0],
                {
                    "trial_id": trial_id,
                    "parent_factor_spec_id": parent_factor_spec_id,
                    "candidate_id": candidate_id,
                    "base_expected_utility": base_expected_utility,
                    "eligible_event_watermark": eligible_event_watermark,
                    "policy_hash": policy_hash,
                    "utility_policy_hash": self.utility_policy.policy_hash,
                    "data_snapshot_hash": data_snapshot_hash,
                    "regime_config_hash": regime_config_hash,
                    "run_group_id": run_group_id,
                    "seed": seed,
                    "candidate_budget": candidate_budget,
                },
            )
            return existing[0]

        starts = self.store.query_events(event_type="TrialStarted", entity_id=trial_id)
        if not starts:
            self.store.append_event(
                EventDraft(
                    event_type="TrialStarted",
                    entity_id=trial_id,
                    run_id=run_id,
                    payload_schema_version="trial_started.v1",
                    idempotency_key=f"trial-start:{trial_id}",
                    payload={
                        "trial_id": trial_id,
                        "candidate_id": candidate_id,
                        "data_scope": "train_valid",
                        "objective": "topology_edit_generation",
                        "started_at": utc_now_iso(),
                    },
                )
            )
        else:
            start = starts[0]
            if start.run_id != run_id or start.payload["candidate_id"] != candidate_id:
                raise ValueError("trial is already bound to another candidate or run")
        payload = {
            "action_id": action_id,
            "trial_id": trial_id,
            "parent_factor_spec_id": parent_factor_spec_id,
            "candidate_id": candidate_id,
            "base_expected_utility": base_expected_utility,
            "eligible_event_watermark": eligible_event_watermark,
            "policy_hash": policy_hash,
            "utility_policy_hash": self.utility_policy.policy_hash,
            "data_snapshot_hash": data_snapshot_hash,
            "regime_config_hash": regime_config_hash,
            "run_group_id": run_group_id,
            "seed": seed,
            "candidate_budget": candidate_budget,
            "frozen_at": utc_now_iso(),
        }
        return self.store.append_event(
            EventDraft(
                event_type="ProcessActionFrozenV2",
                entity_id=action_id,
                run_id=run_id,
                payload_schema_version="process_action_frozen.v2",
                payload=payload,
                idempotency_key=f"process-action-v2:{action_id}",
            )
        )

    def record_outcome(
        self,
        *,
        outcome_id: str,
        action_id: str,
        trial_id: str,
        terminal_event_hash: str,
        evaluation_event_hash: str,
        derivation_event_hash: str,
        child_factor_spec_id: str,
        parent_expression: ExpressionIdentity,
        child_expression: ExpressionIdentity,
        run_id: str,
    ) -> ResearchEventEnvelope:
        action = self._one_event("ProcessActionFrozenV2", action_id)
        evaluation = self._event_by_hash("EvaluationRecorded", evaluation_event_hash)
        evaluation_payload = evaluation.payload
        if evaluation_payload["factor_spec_id"] != child_factor_spec_id:
            raise ValueError("evaluation factor does not match process child")
        if evaluation_payload["data_scope"] not in {"valid", "train_valid"}:
            raise ValueError("process memory accepts terminal train/valid evaluation only")
        scorecard_hash = str(evaluation_payload["scorecard_hash"])
        utility = self._scorecard_utility(
            evaluation,
            child_factor_spec_id=child_factor_spec_id,
            data_snapshot_hash=str(action.payload["data_snapshot_hash"]),
        )
        diff = extract_ast_diff(
            parent_expression.canonical_ast,
            child_expression.canonical_ast,
            parent_expression_id=parent_expression.expression_id,
            child_expression_id=child_expression.expression_id,
            grammar_version=child_expression.grammar_version,
            grammar_hash=child_expression.grammar_hash,
        )
        diff_payload = diff.to_dict()
        payload = {
            "outcome_id": outcome_id,
            "action_id": action_id,
            "trial_id": trial_id,
            "terminal_event_hash": terminal_event_hash,
            "evaluation_event_hash": evaluation_event_hash,
            "derivation_event_hash": derivation_event_hash,
            "data_scope": evaluation_payload["data_scope"],
            "child_factor_spec_id": child_factor_spec_id,
            "observed_validation_utility": utility,
            "scorecard_hash": scorecard_hash,
            "utility_policy_hash": action.payload["utility_policy_hash"],
            "ast_diff": diff_payload,
            "ast_diff_hash": canonical_json_hash(diff_payload),
            "available_at": utc_now_iso(),
            "policy_hash": action.payload["policy_hash"],
            "data_snapshot_hash": action.payload["data_snapshot_hash"],
            "regime_config_hash": action.payload["regime_config_hash"],
            "run_group_id": action.payload["run_group_id"],
        }
        existing = self.store.query_events(
            event_type="ProcessOutcomeRecordedV2", entity_id=outcome_id
        )
        if existing:
            self._require_retry_matches(
                existing[0], {key: value for key, value in payload.items() if key != "available_at"}
            )
            return existing[0]
        return self.store.append_event(
            EventDraft(
                event_type="ProcessOutcomeRecordedV2",
                entity_id=outcome_id,
                run_id=run_id,
                payload_schema_version="process_outcome_recorded.v2",
                payload=payload,
                idempotency_key=f"process-outcome-v2:{action_id}",
            )
        )

    def _scorecard_utility(
        self,
        evaluation: ResearchEventEnvelope,
        *,
        child_factor_spec_id: str,
        data_snapshot_hash: str,
    ) -> float:
        references = [
            ref
            for ref in evaluation.payload["artifact_refs"]
            if ref["artifact_hash"] == evaluation.payload["scorecard_hash"]
            and ref["media_type"] == _SCORECARD_MEDIA_TYPE
        ]
        if len(references) != 1:
            raise ValueError("evaluation must cite exactly one immutable scorecard artifact")
        path = Path(self.store.artifact_root, *str(references[0]["relative_path"]).split("/"))
        if self.store.hash_artifact(path) != evaluation.payload["scorecard_hash"]:
            raise ValueError("scorecard artifact changed after evaluation")
        try:
            scorecard = json.loads(path.read_text(encoding="utf-8"), parse_constant=self._reject_json_constant)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("scorecard artifact is not strict JSON") from exc
        if not isinstance(scorecard, Mapping) or scorecard.get("schema_version") != "alpha_quality_scorecard.v1":
            raise ValueError("unsupported scorecard artifact schema")
        if scorecard.get("factor_id") != child_factor_spec_id or scorecard.get("scope") != "discovery":
            raise ValueError("scorecard factor or scope does not match process evidence")
        if scorecard.get("data_snapshot_ref") != data_snapshot_hash:
            raise ValueError("scorecard data snapshot does not match frozen action")
        try:
            by_horizon = scorecard["predictive"]["by_horizon"]
            values = [
                float(item["by_split"]["valid"]["rank_icir"])
                for item in by_horizon.values()
                if item["by_split"].get("valid", {}).get("rank_icir") is not None
            ]
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise ValueError("scorecard lacks valid RankICIR evidence") from exc
        if not values or any(not math.isfinite(value) for value in values):
            raise ValueError("scorecard validation utility is unavailable or non-finite")
        return sum(values) / len(values)

    def _one_event(self, event_type: str, entity_id: str) -> ResearchEventEnvelope:
        events = self.store.query_events(event_type=event_type, entity_id=entity_id)
        if len(events) != 1:
            raise ValueError(f"expected one {event_type} event")
        return events[0]

    def _event_by_hash(self, event_type: str, event_hash: str) -> ResearchEventEnvelope:
        matches = [
            event for event in self.store.query_events(event_type=event_type)
            if event.event_hash == event_hash
        ]
        if len(matches) != 1:
            raise ValueError(f"unknown {event_type} event hash")
        return matches[0]

    @staticmethod
    def _require_retry_matches(event: ResearchEventEnvelope, expected: Mapping[str, Any]) -> None:
        if any(event.payload.get(key) != value for key, value in expected.items()):
            raise ValueError("idempotent process-memory retry conflicts with existing evidence")

    @staticmethod
    def _reject_json_constant(value: str) -> Any:
        raise ValueError(f"non-finite JSON constant is forbidden: {value}")


__all__ = ["ProcessMemoryService", "ValidationUtilityPolicy"]
