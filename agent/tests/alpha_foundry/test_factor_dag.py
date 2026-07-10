from __future__ import annotations

import pytest

from src.alpha_foundry.dag import (
    FactorDAGError,
    FactorDAGProjector,
    FactorDAGQuery,
    FactorDAGService,
    SimilarityEvidence,
)
from src.alpha_foundry.dsl.identity import FactorIdentityService, FactorSpecSemantics
from src.alpha_quality.flags import ResolvedAGSFlags
from src.research_ledger.events import EventDraft, EventTransitionError, EventValidationError, ResearchEventStore
from src.research_ledger.hash_utils import canonical_json_hash, utc_now_iso


def _flags() -> ResolvedAGSFlags:
    return ResolvedAGSFlags.from_settings(
        {
            "VIBE_TRADING_AGS_ENABLED": "1",
            "VIBE_TRADING_ALPHA_FOUNDRY": "1",
            "VIBE_TRADING_RESEARCH_EVENTS": "1",
            "VIBE_TRADING_FACTOR_DAG": "1",
        }
    )


def _semantics() -> FactorSpecSemantics:
    digest = canonical_json_hash({"fixture": "dag"})
    return FactorSpecSemantics(
        transform_pipeline_hash=digest,
        field_semantics={"close": "pit_eod", "open": "pit_open", "high": "pit_eod"},
        signal_time="session_close_t",
        order_time="next_session_open",
        entry_price_time="next_session_open",
        execution_lag=1,
        return_horizon=5,
        universe_mask_hash=digest,
        tradability_mask_hash=digest,
    )


def _store(tmp_path) -> ResearchEventStore:
    return ResearchEventStore(
        tmp_path / "research.sqlite", artifact_root=tmp_path / "artifacts", flags=_flags(), code_version="dag-test-v1"
    )


def _definition(service: FactorIdentityService, *, trial: str, formula: str):
    result = service.record_attempt(
        trial_id=trial, run_id="run-dag", candidate_id=f"candidate-{trial}", formula=formula, semantics=_semantics()
    )
    assert result.factor_spec_id is not None
    return result.factor_spec_id


def _reject_terminal(store: ResearchEventStore, trial_id: str, factor_spec_id: str):
    evaluation = store.append_event(
        EventDraft(
            event_type="EvaluationRecorded", entity_id=f"evaluation-{trial_id}", run_id="run-dag",
            payload_schema_version="evaluation_recorded.v1",
            payload={
                "evaluation_id": f"evaluation-{trial_id}", "trial_id": trial_id,
                "factor_spec_id": factor_spec_id, "data_scope": "train_valid",
                "scorecard_hash": canonical_json_hash({"trial_id": trial_id}),
                "artifact_refs": [], "metadata": {"fixture": True},
            },
        )
    )
    return store.append_event(
        EventDraft(
            event_type="TrialTerminated", entity_id=trial_id, run_id="run-dag",
            payload_schema_version="trial_terminated.v1", idempotency_key=f"terminal:{trial_id}",
            payload={
                "trial_id": trial_id, "status": "reject", "reason_codes": ["QUALITY_REJECTED"],
                "decision": "reject", "evaluation_event_hash": evaluation.event_hash,
                "terminated_at": utc_now_iso(),
            },
        )
    )


def _lineage(tmp_path):
    store = _store(tmp_path)
    identity = FactorIdentityService(store=store, flags=_flags())
    dag = FactorDAGService(store=store, flags=_flags())
    parent = _definition(identity, trial="trial-parent", formula="rank(close)")
    child = _definition(identity, trial="trial-child", formula="rank(open)")
    terminal = _reject_terminal(store, "trial-child", child)
    edge = dag.record_derivation(
        child_factor_spec_id=child, parent_factor_spec_ids=[parent],
        trial_terminal_event_hash=terminal.event_hash, derivation_kind="mutation", run_id="run-dag"
    )
    return store, dag, parent, child, edge


def test_valid_rejected_factor_remains_in_structural_dag(tmp_path) -> None:
    store, dag, parent, child, edge = _lineage(tmp_path)
    projection = dag.projection()
    query = FactorDAGQuery(projection)

    assert child in projection.factor_nodes
    assert query.ancestors(child) == (parent,)
    assert query.depth(child) == 1
    assert projection.derivation_edges[0].event_hash == edge.event_hash
    assert store.replay().event_count == projection.source_event_count


def test_parse_failure_creates_trial_event_but_no_factor_node(tmp_path) -> None:
    store = _store(tmp_path)
    identity = FactorIdentityService(store=store, flags=_flags())
    result = identity.record_attempt(
        trial_id="trial-invalid", run_id="run-dag", candidate_id="candidate-invalid",
        formula="rank(future_return)", semantics=_semantics()
    )
    projection = FactorDAGProjector(flags=_flags()).project(store.query_events())

    assert result.status == "invalid"
    assert projection.factor_nodes == {}
    assert [event.event_type for event in store.query_events()] == [
        "TrialStarted", "GenerationFailureRecorded", "TrialTerminated"
    ]


def test_missing_parent_self_edge_cycle_and_forged_depth_are_rejected(tmp_path) -> None:
    store, dag, parent, child, _ = _lineage(tmp_path)
    other = _definition(FactorIdentityService(store=store, flags=_flags()), trial="trial-other", formula="rank(high)")
    terminal = _reject_terminal(store, "trial-other", other)

    with pytest.raises(ValueError, match="prior factor definition"):
        dag.record_derivation(child_factor_spec_id=other, parent_factor_spec_ids=["missing"], trial_terminal_event_hash=terminal.event_hash, derivation_kind="mutation", run_id="run-dag")
    with pytest.raises(ValueError, match="self-edge"):
        dag.record_derivation(child_factor_spec_id=other, parent_factor_spec_ids=[other], trial_terminal_event_hash=terminal.event_hash, derivation_kind="mutation", run_id="run-dag")
    with pytest.raises(ValueError, match="cycle"):
        dag.record_derivation(child_factor_spec_id=parent, parent_factor_spec_ids=[child], trial_terminal_event_hash=terminal.event_hash, derivation_kind="mutation", run_id="run-dag")
    with pytest.raises(EventValidationError, match="unknown payload fields"):
        store.append_event(
            EventDraft(
                event_type="DerivationRecorded", entity_id=other, run_id="run-dag", payload_schema_version="derivation_recorded.v1",
                payload={"child_factor_spec_id": other, "parent_factor_spec_ids": [parent], "trial_terminal_event_hash": terminal.event_hash, "derivation_kind": "mutation", "depth": 99},
            )
        )


def test_similarity_evidence_cannot_be_used_as_lineage(tmp_path) -> None:
    _, dag, parent, child, _ = _lineage(tmp_path)
    query = FactorDAGQuery(dag.projection())
    similarity = SimilarityEvidence(parent, child, "factor_rank_correlation", canonical_json_hash({"rho": 0.99}))

    assert query.accepts_similarity_as_lineage(similarity) is False
    assert query.lineage_edges()[0].parent_factor_spec_ids == (parent,)


def test_factor_dag_flag_off_refuses_projection_construction() -> None:
    flags = ResolvedAGSFlags.from_settings({"VIBE_TRADING_AGS_ENABLED": "1"})
    with pytest.raises(RuntimeError, match="disabled"):
        FactorDAGProjector(flags=flags)


def test_factor_dag_child_flag_cannot_bypass_foundry_parent(tmp_path) -> None:
    flags = ResolvedAGSFlags.from_settings(
        {
            "VIBE_TRADING_AGS_ENABLED": "1",
            "VIBE_TRADING_RESEARCH_EVENTS": "1",
            "VIBE_TRADING_FACTOR_DAG": "1",
        }
    )
    store = ResearchEventStore(
        tmp_path / "research.sqlite", artifact_root=tmp_path / "artifacts",
        flags=flags, code_version="dag-disabled-test-v1",
    )
    with pytest.raises(RuntimeError, match="disabled"):
        FactorDAGService(store=store, flags=flags)


def test_derivation_terminal_must_belong_to_child_and_be_evaluated(tmp_path) -> None:
    store = _store(tmp_path)
    identity = FactorIdentityService(store=store, flags=_flags())
    dag = FactorDAGService(store=store, flags=_flags())
    parent = _definition(identity, trial="trial-parent", formula="rank(close)")
    child = _definition(identity, trial="trial-child", formula="rank(open)")
    other = _definition(identity, trial="trial-other", formula="rank(high)")
    unrelated = _reject_terminal(store, "trial-other", other)

    with pytest.raises(EventTransitionError, match="bound to the child trial"):
        dag.record_derivation(
            child_factor_spec_id=child, parent_factor_spec_ids=[parent],
            trial_terminal_event_hash=unrelated.event_hash,
            derivation_kind="mutation", run_id="run-dag",
        )

    unevaluated = store.append_event(
        EventDraft(
            event_type="TrialTerminated", entity_id="trial-child", run_id="run-dag",
            payload_schema_version="trial_terminated.v1",
            payload={
                "trial_id": "trial-child", "status": "reject",
                "reason_codes": ["QUALITY_REJECTED"], "decision": "reject",
                "evaluation_event_hash": None, "terminated_at": utc_now_iso(),
            },
        )
    )
    with pytest.raises(EventTransitionError, match="matching train/valid evaluation"):
        dag.record_derivation(
            child_factor_spec_id=child, parent_factor_spec_ids=[parent],
            trial_terminal_event_hash=unevaluated.event_hash,
            derivation_kind="mutation", run_id="run-dag",
        )


def test_multi_parent_depth_is_derived_and_unknown_queries_fail_closed(tmp_path) -> None:
    store = _store(tmp_path)
    identity = FactorIdentityService(store=store, flags=_flags())
    dag = FactorDAGService(store=store, flags=_flags())
    parent_one = _definition(identity, trial="trial-p1", formula="rank(close)")
    parent_two = _definition(identity, trial="trial-p2", formula="rank(open)")
    child = _definition(identity, trial="trial-c", formula="rank(high)")
    terminal = _reject_terminal(store, "trial-c", child)
    dag.record_derivation(
        child_factor_spec_id=child, parent_factor_spec_ids=[parent_one, parent_two],
        trial_terminal_event_hash=terminal.event_hash,
        derivation_kind="crossover", run_id="run-dag",
    )
    query = FactorDAGQuery(dag.projection())

    assert query.ancestors(child) == tuple(sorted((parent_one, parent_two)))
    assert query.depth(child) == 1
    with pytest.raises(KeyError):
        query.ancestors("caller-forged-factor")
