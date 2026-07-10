"""Deterministic append helpers for frozen action and process outcome events."""

from __future__ import annotations

from src.alpha_foundry.dsl.diff import extract_ast_diff
from src.alpha_foundry.dsl.identity import ExpressionIdentity
from src.alpha_quality.flags import ResolvedAGSFlags
from src.research_ledger.events import EventDraft, ResearchEventStore
from src.research_ledger.hash_utils import canonical_json_hash, utc_now_iso


class ProcessMemoryService:
    def __init__(self, *, store: ResearchEventStore, flags: ResolvedAGSFlags) -> None:
        if not flags.enabled("VIBE_TRADING_PROCESS_MEMORY"):
            raise RuntimeError("process memory capability is disabled")
        self.store = store

    def freeze_action(self, *, action_id: str, trial_id: str, parent_factor_spec_id: str, candidate_id: str, base_expected_utility: float, eligible_event_watermark: str | None, policy_hash: str, seed: int, candidate_budget: int, run_id: str):
        payload = {"action_id": action_id, "trial_id": trial_id, "parent_factor_spec_id": parent_factor_spec_id, "candidate_id": candidate_id, "base_expected_utility": base_expected_utility, "eligible_event_watermark": eligible_event_watermark, "policy_hash": policy_hash, "seed": seed, "candidate_budget": candidate_budget, "frozen_at": utc_now_iso()}
        return self.store.append_event(EventDraft(event_type="ProcessActionFrozen", entity_id=action_id, run_id=run_id, payload_schema_version="process_action_frozen.v1", payload=payload, idempotency_key=f"process-action:{action_id}"))

    def record_outcome(self, *, outcome_id: str, action_id: str, trial_id: str, terminal_event_hash: str, data_scope: str, child_factor_spec_id: str | None, parent_expression: ExpressionIdentity | None, child_expression: ExpressionIdentity | None, observed_validation_utility: float | None, policy_hash: str, run_id: str):
        if data_scope not in {"train", "valid", "train_valid"}:
            raise ValueError("process memory accepts train/valid evidence only")
        if child_factor_spec_id is None:
            if parent_expression is not None or child_expression is not None or observed_validation_utility is not None:
                raise ValueError("invalid process outcome cannot supply child evidence")
            diff = None
        else:
            if parent_expression is None or child_expression is None or observed_validation_utility is None:
                raise ValueError("terminal child evidence requires identities and validation utility")
            diff = extract_ast_diff(parent_expression.canonical_ast, child_expression.canonical_ast, parent_expression_id=parent_expression.expression_id, child_expression_id=child_expression.expression_id, grammar_version=child_expression.grammar_version, grammar_hash=child_expression.grammar_hash).to_dict()
        payload = {"outcome_id": outcome_id, "action_id": action_id, "trial_id": trial_id, "terminal_event_hash": terminal_event_hash, "data_scope": data_scope, "child_factor_spec_id": child_factor_spec_id, "observed_validation_utility": observed_validation_utility, "ast_diff": diff, "available_at": utc_now_iso(), "policy_hash": policy_hash}
        return self.store.append_event(EventDraft(event_type="ProcessOutcomeRecorded", entity_id=outcome_id, run_id=run_id, payload_schema_version="process_outcome_recorded.v1", payload=payload, idempotency_key="process-outcome:" + canonical_json_hash(payload)))


__all__ = ["ProcessMemoryService"]
