from __future__ import annotations

import pytest

from src.alpha_foundry.dag import FactorDAGService
from src.alpha_foundry.dsl.identity import FactorIdentityService, FactorSpecSemantics
from src.alpha_foundry.memory import EpisodicProjector, ProcessMemoryService, WorkingMemory
from src.alpha_foundry.memory.model import ProcessMemoryObservation
from src.alpha_quality.flags import ResolvedAGSFlags
from src.research_ledger.events import EventDraft, ResearchEventStore
from src.research_ledger.hash_utils import canonical_json_hash, utc_now_iso


def _flags() -> ResolvedAGSFlags:
    return ResolvedAGSFlags.from_settings({"VIBE_TRADING_AGS_ENABLED": "1", "VIBE_TRADING_ALPHA_FOUNDRY": "1", "VIBE_TRADING_RESEARCH_EVENTS": "1", "VIBE_TRADING_FACTOR_DAG": "1", "VIBE_TRADING_PROCESS_MEMORY": "1"})


def _semantics() -> FactorSpecSemantics:
    digest = canonical_json_hash({"memory": "fixture"})
    return FactorSpecSemantics(transform_pipeline_hash=digest, field_semantics={"close": "pit", "open": "pit"}, signal_time="close", order_time="open", entry_price_time="open", execution_lag=1, return_horizon=5, universe_mask_hash=digest, tradability_mask_hash=digest)


def _store(tmp_path) -> ResearchEventStore:
    return ResearchEventStore(tmp_path / "research.sqlite", artifact_root=tmp_path / "artifacts", flags=_flags(), code_version="memory-test")


def _terminal(store: ResearchEventStore, trial_id: str):
    return store.append_event(EventDraft(event_type="TrialTerminated", entity_id=trial_id, run_id="run", payload_schema_version="trial_terminated.v1", idempotency_key=f"terminal:{trial_id}", payload={"trial_id": trial_id, "status": "reject", "reason_codes": ["QUALITY_REJECTED"], "decision": "reject", "evaluation_event_hash": None, "terminated_at": utc_now_iso()}))


def _record_valid_outcome(tmp_path):
    store = _store(tmp_path)
    identity = FactorIdentityService(store=store, flags=_flags())
    dag = FactorDAGService(store=store, flags=_flags())
    memory = ProcessMemoryService(store=store, flags=_flags())
    parent = identity.record_attempt(trial_id="parent", run_id="run", candidate_id="parent", formula="rank(close)", semantics=_semantics())
    child = identity.record_attempt(trial_id="child", run_id="run", candidate_id="child", formula="zscore(rank(open))", semantics=_semantics())
    assert parent.factor_spec_id and child.factor_spec_id
    policy_hash = canonical_json_hash({"policy": "v1"})
    action = memory.freeze_action(action_id="action-1", trial_id="child", parent_factor_spec_id=parent.factor_spec_id, candidate_id="child", base_expected_utility=0.10, eligible_event_watermark=None, policy_hash=policy_hash, seed=7, candidate_budget=10, run_id="run")
    terminal = _terminal(store, "child")
    derivation = dag.record_derivation(child_factor_spec_id=child.factor_spec_id, parent_factor_spec_ids=[parent.factor_spec_id], trial_terminal_event_hash=terminal.event_hash, derivation_kind="mutation", run_id="run")
    outcome = memory.record_outcome(outcome_id="outcome-1", action_id="action-1", trial_id="child", terminal_event_hash=terminal.event_hash, data_scope="valid", child_factor_spec_id=child.factor_spec_id, parent_expression=parent.expression if hasattr(parent, "expression") else None, child_expression=child.expression if hasattr(child, "expression") else None, observed_validation_utility=0.30, policy_hash=policy_hash, run_id="run")
    return store, action, derivation, outcome


def test_motif_is_derived_from_diff_and_records_extractor_version(tmp_path) -> None:
    store, _, derivation, _ = _record_valid_outcome(tmp_path)
    projection = EpisodicProjector().project(store.query_events())

    assert len(projection.observations) == 1
    observation = projection.observations[0]
    assert observation.derivation_event_hash == derivation.event_hash
    assert observation.motif_version == "ast-motif.v1"
    assert observation.motif


def test_nonterminal_events_and_final_scope_do_not_update_memory(tmp_path) -> None:
    store = _store(tmp_path)
    identity = FactorIdentityService(store=store, flags=_flags())
    memory = ProcessMemoryService(store=store, flags=_flags())
    parent = identity.record_attempt(trial_id="parent", run_id="run", candidate_id="parent", formula="rank(close)", semantics=_semantics())
    child = identity.record_attempt(trial_id="child", run_id="run", candidate_id="child", formula="rank(open)", semantics=_semantics())
    assert parent.factor_spec_id
    memory.freeze_action(action_id="action-open", trial_id="child", parent_factor_spec_id=parent.factor_spec_id, candidate_id="child", base_expected_utility=0.1, eligible_event_watermark=None, policy_hash=canonical_json_hash({"policy": "v1"}), seed=1, candidate_budget=2, run_id="run")

    assert EpisodicProjector().project(store.query_events()).observations == ()
    with pytest.raises(ValueError, match="train/valid"):
        memory.record_outcome(outcome_id="final", action_id="action-open", trial_id="child", terminal_event_hash="sha256:" + "a" * 64, data_scope="final_test", child_factor_spec_id=child.factor_spec_id, parent_expression=None, child_expression=None, observed_validation_utility=None, policy_hash=canonical_json_hash({"policy": "v1"}), run_id="run")


def test_positive_memory_adjustment_is_bounded_and_low_confidence_shrinks() -> None:
    projector = EpisodicProjector(minimum_effective_count=3, max_positive_adjustment=0.05)
    observations = [ProcessMemoryObservation("ctx", "parent", f"child-{index}", "edge", "diff", "v1", "Wrap:rank", 0.0, 5.0, 5.0, "reject", (), None, "policy", "now") for index in range(3)]
    posterior = projector._posteriors(observations)[0]
    low = EpisodicProjector(minimum_effective_count=5)._posteriors(observations[:1])[0]

    assert posterior.positive_adjustment == 0.05
    assert low.confidence < 1.0
    assert low.positive_adjustment < 5.0


def test_working_memory_is_bounded_and_not_event_persisted(tmp_path) -> None:
    working = WorkingMemory(capacity=2)
    working.add("one", {"score": 1})
    working.add("two", {"score": 2})
    working.add("three", {"score": 3})

    assert [item.candidate_id for item in working.snapshot()] == ["two", "three"]
    assert _store(tmp_path).query_events() == []


def test_process_memory_flag_off_refuses_service(tmp_path) -> None:
    flags = ResolvedAGSFlags.from_settings({"VIBE_TRADING_AGS_ENABLED": "1", "VIBE_TRADING_RESEARCH_EVENTS": "1"})
    store = ResearchEventStore(tmp_path / "db.sqlite", artifact_root=tmp_path / "artifacts", flags=flags, code_version="test")
    with pytest.raises(RuntimeError, match="disabled"):
        ProcessMemoryService(store=store, flags=flags)
