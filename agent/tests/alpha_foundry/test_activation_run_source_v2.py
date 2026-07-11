from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from src.alpha_foundry.activation import (
    ActivationEvidenceService,
    ActivationRunManifest,
    ActivationRunSourceAuditorV2,
)
from src.research_ledger.events import EventDraft
from src.research_ledger.hash_utils import canonical_json_hash
from test_activation_retriever import event_store, manifest, plan


def test_v1_summary_without_source_events_is_explicitly_ineligible(
    tmp_path: Path,
) -> None:
    frozen = plan()
    store = event_store(tmp_path)
    ActivationEvidenceService(store).register_plan(frozen)
    summary = manifest(frozen, "group-00", "treatment")

    audit = ActivationRunSourceAuditorV2(store).audit(
        summary,
        retriever_decision_event_hashes=(),
        terminal_event_hashes=(),
        evaluation_event_hashes=(),
        quality_decision_event_hashes=(),
    )

    assert audit.schema_version == "activation_run_source.v2"
    assert audit.source_complete is False
    assert {
        "RETRIEVER_V3_SOURCE_MISSING",
        "TERMINAL_SOURCE_MISSING",
        "EVALUATION_SOURCE_MISSING",
        "QUALITY_DECISION_V3_SOURCE_MISSING",
        "RESOURCE_METRICS_SOURCE_UNBOUND",
        "QUALITY_DECISION_UPSTREAM_AUTHORITY_UNPROVEN",
        "TERMINAL_STATUS_SUMMARY_MISMATCH",
        "CANDIDATE_ID_SUMMARY_MISMATCH",
        "EFFECTIVE_CANDIDATE_SUMMARY_MISMATCH",
        "FIXED_CANDIDATE_BUDGET_INCOMPLETE",
    }.issubset(audit.source_failure_codes)
    assert audit == ActivationRunSourceAuditorV2(store).audit(
        summary,
        retriever_decision_event_hashes=(),
        terminal_event_hashes=(),
        evaluation_event_hashes=(),
        quality_decision_event_hashes=(),
    )


def test_source_audit_rejects_duplicate_hashes_and_caller_hash_rewrite(
    tmp_path: Path,
) -> None:
    frozen = plan()
    store = event_store(tmp_path)
    plan_event_count = len(store.query_events())
    ActivationEvidenceService(store).register_plan(frozen)
    summary = manifest(frozen, "group-00", "control")
    digest = canonical_json_hash({"missing": "source"})
    audit = ActivationRunSourceAuditorV2(store).audit(
        summary,
        retriever_decision_event_hashes=(digest, digest),
        terminal_event_hashes=(),
        evaluation_event_hashes=(),
        quality_decision_event_hashes=(),
    )
    assert "DUPLICATE_SOURCE_EVENT_HASH" in audit.source_failure_codes
    assert "CONTROL_POLICY_SOURCE_UNBOUND" in audit.source_failure_codes
    assert len(store.query_events()) == plan_event_count + 1
    with pytest.raises(ValueError, match="audit hash"):
        replace(audit, audit_hash=canonical_json_hash({"caller": "rewrite"}))
    with pytest.raises(ValueError, match="canonical sha256"):
        ActivationRunSourceAuditorV2(store).audit(
            summary,
            retriever_decision_event_hashes=("not-a-hash",),
            terminal_event_hashes=(),
            evaluation_event_hashes=(),
            quality_decision_event_hashes=(),
        )


def test_terminal_counts_and_candidate_ids_rebuild_from_chain(tmp_path: Path) -> None:
    frozen = plan()
    store = event_store(tmp_path)
    ActivationEvidenceService(store).register_plan(frozen)
    candidate_ids = tuple(f"group-00-treatment-{index}" for index in range(4))
    summary = ActivationRunManifest.create(
        plan_hash=frozen.plan_hash,
        pair_id="group-00:momentum:leaf",
        run_group_id="group-00",
        arm="treatment",
        seed=frozen.design.seeds[0],
        data_snapshot_hash=frozen.provenance.train_snapshot_hash,
        mechanism_family="momentum",
        dag_region="leaf",
        policy_hash=frozen.provenance.treatment_policy_hash,
        rng_namespace=f"{frozen.plan_hash}:group-00:treatment:rng",
        cache_namespace=f"{frozen.plan_hash}:group-00:treatment:cache",
        candidate_budget=4,
        compute_budget=8,
        terminal_status_counts={
            "success": 0, "reject": 0, "skip": 0, "invalid": 0,
            "duplicate": 4, "timeout": 0, "error": 0,
            "infrastructure_failure": 0,
        },
        candidate_ids=candidate_ids,
        effective_candidate_ids=(),
        metrics={
            "duplicate_rate": 1.0,
            "failure_rate": 0.0,
            "propensity_unexplained_fraction": 0.0,
            "coverage_coverage_collapse": 0.0,
            "resource_wall_seconds": 1.0,
        },
        started_at="2026-07-11T00:00:00Z",
        ended_at="2026-07-11T00:00:01Z",
        complete=True,
    )
    terminal_hashes: list[str] = []
    for index, candidate_id in enumerate(candidate_ids):
        trial_id = f"source-trial-{index}"
        store.append_event(
            EventDraft(
                event_type="TrialStarted",
                entity_id=trial_id,
                run_id="group-00",
                payload_schema_version="trial_started.v1",
                payload={
                    "trial_id": trial_id,
                    "candidate_id": candidate_id,
                    "data_scope": "train_valid",
                    "objective": "activation-source-v2",
                    "started_at": "2026-07-11T00:00:00Z",
                },
            )
        )
        terminal_hashes.append(
            store.append_event(
                EventDraft(
                    event_type="TrialTerminated",
                    entity_id=trial_id,
                    run_id="group-00",
                    payload_schema_version="trial_terminated.v1",
                    payload={
                        "trial_id": trial_id,
                        "status": "duplicate",
                        "reason_codes": ["DUPLICATE_IDENTITY"],
                        "decision": "reject",
                        "evaluation_event_hash": None,
                        "terminated_at": "2026-07-11T00:00:01Z",
                    },
                )
            ).event_hash
        )
    audit = ActivationRunSourceAuditorV2(store).audit(
        summary,
        retriever_decision_event_hashes=(),
        terminal_event_hashes=tuple(terminal_hashes),
        evaluation_event_hashes=(),
        quality_decision_event_hashes=(),
    )
    assert dict(audit.derived_terminal_status_counts)["duplicate"] == 4
    assert audit.derived_candidate_ids == candidate_ids
    assert "TERMINAL_STATUS_SUMMARY_MISMATCH" not in audit.source_failure_codes
    assert "CANDIDATE_ID_SUMMARY_MISMATCH" not in audit.source_failure_codes
    assert audit.source_complete is False
