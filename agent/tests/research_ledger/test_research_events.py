from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.alpha_quality.flags import ResolvedAGSFlags
from src.research_ledger.events import (
    ArtifactReferenceError,
    EventDraft,
    EventIdempotencyConflict,
    EventMutationError,
    EventTransitionError,
    EventValidationError,
    ResearchEventAppendError,
    ResearchEventStore,
    PAYLOAD_SPECS,
)
from src.research_ledger.events.payloads import validate_and_redact_payload
from src.research_ledger.trial_ledger import TrialLedger, TrialLedgerEntry


def _flags(*, enabled: bool = True) -> ResolvedAGSFlags:
    settings = {}
    if enabled:
        settings = {
            "VIBE_TRADING_AGS_ENABLED": "1",
            "VIBE_TRADING_RESEARCH_EVENTS": "1",
        }
    return ResolvedAGSFlags.from_settings(settings)


def _store(
    tmp_path: Path,
    *,
    enabled: bool = True,
    durability_profile: str = "authoritative",
) -> ResearchEventStore:
    return ResearchEventStore(
        tmp_path / "research.sqlite",
        artifact_root=tmp_path / "artifacts",
        flags=_flags(enabled=enabled),
        code_version="test-code-v1",
        durability_profile=durability_profile,
    )


def _factor_payload(factor_spec_id: str = "factor-spec-1") -> dict[str, object]:
    return {
        "factor_spec_id": factor_spec_id,
        "expression_id": "expression-1",
        "canonical_ast_hash": "sha256:" + "a" * 64,
        "grammar_version": "1.0.0",
        "grammar_hash": "sha256:" + "b" * 64,
        "metadata": {},
        "artifact_refs": [],
    }


def _draft(
    *,
    event_type: str = "FactorDefinitionRecorded",
    entity_id: str = "factor-spec-1",
    payload: dict[str, object] | None = None,
    payload_schema_version: str | None = None,
    idempotency_key: str | None = None,
) -> EventDraft:
    return EventDraft(
        event_type=event_type,
        entity_id=entity_id,
        run_id="run-1",
        payload_schema_version=(
            payload_schema_version
            or {
                "FactorDefinitionRecorded": "factor_definition_recorded.v1",
                "TrialStarted": "trial_started.v1",
                "TrialTerminated": "trial_terminated.v1",
                "EvaluationRecorded": "evaluation_recorded.v1",
            }.get(event_type, "unknown.v1")
        ),
        payload=payload if payload is not None else _factor_payload(),
        idempotency_key=idempotency_key,
    )


def test_payload_hash_is_deterministic_but_event_hash_represents_each_append(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)

    first = store.append_event(_draft())
    second = store.append_event(_draft())

    assert first.payload_hash == second.payload_hash
    assert first.event_id != second.event_id
    assert first.event_hash != second.event_hash
    assert second.previous_event_hash == first.event_hash
    assert store.verify_chain()
    with pytest.raises(TypeError):
        first.payload["factor_spec_id"] = "mutated"  # type: ignore[index]
    with pytest.raises(TypeError):
        first.feature_flags["VIBE_TRADING_RESEARCH_EVENTS"] = False  # type: ignore[index]


def test_idempotent_retry_returns_existing_event_and_conflict_is_rejected(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    draft = _draft(idempotency_key="factor-definition:1")

    first = store.append_event(draft)
    retried = store.append_event(draft)

    assert retried == first
    assert len(store.query_events()) == 1
    with pytest.raises(EventIdempotencyConflict):
        store.append_event(
            _draft(
                idempotency_key="factor-definition:1",
                entity_id="factor-spec-conflict",
                payload=_factor_payload("factor-spec-conflict"),
            )
        )
    balanced = ResearchEventStore(
        tmp_path / "research.sqlite",
        artifact_root=tmp_path / "artifacts",
        flags=_flags(),
        code_version="test-code-v1",
        durability_profile="balanced",
    )
    with pytest.raises(EventIdempotencyConflict):
        balanced.append_event(draft)


def test_unknown_event_payload_version_and_unknown_fields_are_rejected(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)

    with pytest.raises(EventValidationError, match="unknown event type"):
        store.append_event(_draft(event_type="CallerInventedEvent"))
    with pytest.raises(EventValidationError, match="payload schema version"):
        store.append_event(_draft(payload_schema_version="factor_definition_recorded.v999"))
    bad = _factor_payload()
    bad["is_terminal"] = True
    with pytest.raises(EventValidationError, match="unknown payload fields"):
        store.append_event(_draft(payload=bad))


def test_closed_payload_registry_covers_every_required_event_type() -> None:
    assert set(PAYLOAD_SPECS) == {
        "TrialStarted",
        "FactorDefinitionRecorded",
        "RegistryBootstrapRecorded",
        "DerivationRecorded",
        "GenerationFailureRecorded",
        "EvaluationRecorded",
        "TrialTerminated",
        "RetrieverDecisionRecorded",
        "FalsificationContractRegistered",
        "FalsificationResultRecorded",
        "QualityDecisionRecorded",
        "ForwardPlanRecorded",
        "ForwardObservationRecorded",
    }
    assert len({spec.version for spec in PAYLOAD_SPECS.values()}) == len(PAYLOAD_SPECS)
    with pytest.raises(TypeError):
        PAYLOAD_SPECS["CallerInventedEvent"] = PAYLOAD_SPECS["TrialStarted"]  # type: ignore[index]
    with pytest.raises(TypeError):
        PAYLOAD_SPECS["TrialStarted"].fields["is_terminal"] = lambda value, path: None  # type: ignore[index]


def test_every_registered_payload_schema_validates_a_complete_production_shape() -> None:
    digest = "sha256:" + "d" * 64
    timestamp = "2025-01-01T00:00:00Z"
    samples: dict[str, dict[str, object]] = {
        "TrialStarted": {
            "trial_id": "trial-1",
            "candidate_id": "candidate-1",
            "data_scope": "train_valid",
            "objective": "rank_ic",
            "started_at": timestamp,
        },
            "FactorDefinitionRecorded": _factor_payload(),
            "RegistryBootstrapRecorded": {
                "snapshot_id": "registry-1",
                "registry_snapshot_hash": digest,
                "registry_code_hash": digest,
                "grammar_hash": digest,
                "roots": [
                    {
                        "alpha_id": "fixture_alpha",
                        "status": "legacy_opaque",
                        "expression_id": None,
                        "legacy_formula_hash": digest,
                    }
                ],
            },
            "DerivationRecorded": {
            "child_factor_spec_id": "child-1",
            "parent_factor_spec_ids": ["parent-1", "parent-2"],
            "trial_terminal_event_hash": digest,
            "derivation_kind": "crossover",
        },
        "GenerationFailureRecorded": {
            "trial_id": "trial-1",
            "failure_code": "INVALID_FORMULA",
            "failure_kind": "invalid",
            "message": "formula did not parse",
            "occurred_at": timestamp,
        },
        "EvaluationRecorded": {
            "evaluation_id": "evaluation-1",
            "trial_id": "trial-1",
            "factor_spec_id": "factor-1",
            "data_scope": "train_valid",
            "scorecard_hash": digest,
            "artifact_refs": [],
            "metadata": {},
        },
        "TrialTerminated": {
            "trial_id": "trial-1",
            "status": "reject",
            "reason_codes": ["QUALITY_REJECTED"],
            "decision": "reject",
            "evaluation_event_hash": None,
            "terminated_at": timestamp,
        },
        "RetrieverDecisionRecorded": {
            "decision_id": "retriever-1",
            "selected_factor_spec_ids": ["factor-1"],
            "selection_propensity": 0.5,
            "seed": 7,
            "policy_hash": digest,
            "eligible_event_watermark": digest,
            "veto_reason": None,
        },
        "FalsificationContractRegistered": {
            "contract_id": "contract-1",
            "contract_hash": digest,
            "factor_spec_id": "factor-1",
            "registered_at": timestamp,
            "data_access_cutoff": timestamp,
            "policy_hash": digest,
        },
        "FalsificationResultRecorded": {
            "result_id": "result-1",
            "contract_id": "contract-1",
            "contract_hash": digest,
            "outcome": "inconclusive",
            "artifact_refs": [],
        },
        "QualityDecisionRecorded": {
            "decision_id": "quality-1",
            "factor_spec_id": "factor-1",
            "decision": "research_only",
            "policy_hash": digest,
            "evidence_hashes": [digest],
            "reasons": ["EVIDENCE_BOUNDED"],
            "warnings": ["LIMITED_SAMPLE"],
            "caps": ["MISSING_EXECUTION"],
            "limitations": ["research evidence only"],
        },
        "ForwardPlanRecorded": {
            "plan_id": "plan-1",
            "factor_spec_id": "factor-1",
            "plan_hash": digest,
            "minimum_observations": 12,
            "policy_hash": digest,
        },
        "ForwardObservationRecorded": {
            "observation_id": "observation-1",
            "plan_id": "plan-1",
            "period_start": timestamp,
            "period_end": timestamp,
            "observation_hash": digest,
            "previous_observation_hash": None,
            "artifact_refs": [],
        },
    }

    for event_type, spec in PAYLOAD_SPECS.items():
        validated = validate_and_redact_payload(event_type, spec.version, samples[event_type])
        assert set(validated) == set(spec.fields)


def test_non_finite_values_rejected_before_redaction_and_secrets_paths_redacted(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    bad = _factor_payload()
    bad["metadata"] = {"metric": math.nan}

    with pytest.raises(EventValidationError, match="non-finite"):
        store.append_event(_draft(payload=bad))

    payload = _factor_payload()
    payload["metadata"] = {
        "api_key": "sk-super-secret",
        "nested": {
            "cache_path": r"C:\private\factor.parquet",
            "account_id": "private-account-123",
            "environment": {"HOME": "/home/private-user"},
            "message": "/home/private-user/factor.parquet",
            "safe": "kept",
        },
    }
    event = store.append_event(_draft(payload=payload))
    encoded = json.dumps(event.to_dict(), sort_keys=True)

    assert "sk-super-secret" not in encoded
    assert r"C:\private" not in encoded
    assert "private-account-123" not in encoded
    assert "/home/private-user" not in encoded
    assert event.payload["metadata"]["api_key"] == "[redacted]"
    assert event.payload["metadata"]["nested"]["safe"] == "kept"


def test_secret_or_absolute_path_in_envelope_identity_is_rejected(tmp_path: Path) -> None:
    store = _store(tmp_path)

    with pytest.raises(EventValidationError, match="entity_id contains secret or local path"):
        store.append_event(_draft(entity_id="sk-super-secret-value"))
    with pytest.raises(EventValidationError, match="idempotency_key contains secret or local path"):
        store.append_event(_draft(idempotency_key=r"C:\private\request.key"))


def test_artifact_reference_requires_containment_existence_and_content_hash(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    artifact = tmp_path / "artifacts" / "panels" / "factor.bin"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"factor-panel")
    payload = _factor_payload()
    payload["artifact_refs"] = [
        {
            "relative_path": "panels/factor.bin",
            "artifact_hash": ResearchEventStore.hash_artifact(artifact),
            "media_type": "application/octet-stream",
        }
    ]

    event = store.append_event(_draft(payload=payload))

    assert event.payload["artifact_refs"][0]["relative_path"] == "panels/factor.bin"
    wrong_hash = _factor_payload()
    wrong_hash["artifact_refs"] = [
        {
            "relative_path": "panels/factor.bin",
            "artifact_hash": "sha256:" + "0" * 64,
            "media_type": "application/octet-stream",
        }
    ]
    with pytest.raises(ArtifactReferenceError, match="hash mismatch"):
        store.append_event(_draft(payload=wrong_hash))
    traversal = _factor_payload()
    traversal["artifact_refs"] = [
        {
            "relative_path": "../outside.bin",
            "artifact_hash": "sha256:" + "0" * 64,
            "media_type": "application/octet-stream",
        }
    ]
    with pytest.raises(ArtifactReferenceError, match="relative artifact path"):
        store.append_event(_draft(payload=traversal))
    encoded = _factor_payload()
    encoded["artifact_refs"] = [
        {
            "relative_path": "%2e%2e/outside.bin",
            "artifact_hash": "sha256:" + "0" * 64,
            "media_type": "application/octet-stream",
        }
    ]
    with pytest.raises(ArtifactReferenceError, match="encoded relative artifact path"):
        store.append_event(_draft(payload=encoded))


@pytest.mark.parametrize(
    "terminal_status",
    [
        "success",
        "reject",
        "skip",
        "invalid",
        "duplicate",
        "timeout",
        "error",
        "infrastructure_failure",
    ],
)
def test_every_started_trial_has_exactly_one_typed_terminal_outcome(
    tmp_path: Path,
    terminal_status: str,
) -> None:
    store = _store(tmp_path)
    trial_id = f"trial-{terminal_status}"
    store.append_event(
        _draft(
            event_type="TrialStarted",
            entity_id=trial_id,
            payload={
                "trial_id": trial_id,
                "candidate_id": f"candidate-{terminal_status}",
                "data_scope": "train_valid",
                "objective": "rank_ic",
                "started_at": "2025-01-01T00:00:00Z",
            },
        )
    )
    decision = "candidate_zoo" if terminal_status == "success" else "none"
    evaluation_event_hash = None
    if terminal_status == "success":
        evaluation = store.append_event(
            _draft(
                event_type="EvaluationRecorded",
                entity_id=f"evaluation-{trial_id}",
                payload={
                    "evaluation_id": f"evaluation-{trial_id}",
                    "trial_id": trial_id,
                    "factor_spec_id": f"factor-{trial_id}",
                    "data_scope": "train_valid",
                    "scorecard_hash": "sha256:" + "c" * 64,
                    "artifact_refs": [],
                    "metadata": {},
                },
            )
        )
        evaluation_event_hash = evaluation.event_hash
    terminal = store.append_event(
        _draft(
            event_type="TrialTerminated",
            entity_id=trial_id,
            payload={
                "trial_id": trial_id,
                "status": terminal_status,
                "reason_codes": [] if terminal_status == "success" else [terminal_status.upper()],
                "decision": decision,
                "evaluation_event_hash": evaluation_event_hash,
                "terminated_at": "2025-01-01T00:01:00Z",
            },
        )
    )

    assert terminal.payload["status"] == terminal_status
    assert store.lifecycle_summary().open_trial_ids == ()
    with pytest.raises(EventTransitionError, match="already terminated"):
        store.append_event(
            _draft(
                event_type="TrialTerminated",
                entity_id=trial_id,
                payload=dict(terminal.payload),
            )
        )


def test_terminal_requires_start_and_infrastructure_cannot_promote(tmp_path: Path) -> None:
    store = _store(tmp_path)
    payload = {
        "trial_id": "trial-orphan",
        "status": "infrastructure_failure",
        "reason_codes": ["WORKER_CRASH"],
        "decision": "paper_candidate",
        "evaluation_event_hash": None,
        "terminated_at": "2025-01-01T00:01:00Z",
    }

    with pytest.raises(EventValidationError, match="cannot promote"):
        store.append_event(
            _draft(event_type="TrialTerminated", entity_id="trial-orphan", payload=payload)
        )
    payload["decision"] = "none"
    with pytest.raises(EventTransitionError, match="was not started"):
        store.append_event(
            _draft(event_type="TrialTerminated", entity_id="trial-orphan", payload=payload)
        )


def test_out_of_order_cross_event_references_are_rejected(tmp_path: Path) -> None:
    store = _store(tmp_path)
    digest = "sha256:" + "d" * 64

    with pytest.raises(EventTransitionError, match="prior terminal trial"):
        store.append_event(
            EventDraft(
                event_type="DerivationRecorded",
                entity_id="child-1",
                run_id="run-1",
                payload_schema_version="derivation_recorded.v1",
                payload={
                    "child_factor_spec_id": "child-1",
                    "parent_factor_spec_ids": ["parent-1"],
                    "trial_terminal_event_hash": digest,
                    "derivation_kind": "mutation",
                },
            )
        )
    with pytest.raises(EventTransitionError, match="prior contract"):
        store.append_event(
            EventDraft(
                event_type="FalsificationResultRecorded",
                entity_id="result-1",
                run_id="run-1",
                payload_schema_version="falsification_result_recorded.v1",
                payload={
                    "result_id": "result-1",
                    "contract_id": "contract-1",
                    "contract_hash": digest,
                    "outcome": "inconclusive",
                    "artifact_refs": [],
                },
            )
        )
    with pytest.raises(EventTransitionError, match="prior plan"):
        store.append_event(
            EventDraft(
                event_type="ForwardObservationRecorded",
                entity_id="observation-1",
                run_id="run-1",
                payload_schema_version="forward_observation_recorded.v1",
                payload={
                    "observation_id": "observation-1",
                    "plan_id": "plan-1",
                    "period_start": "2025-01-01T00:00:00Z",
                    "period_end": "2025-01-02T00:00:00Z",
                    "observation_hash": digest,
                    "previous_observation_hash": None,
                    "artifact_refs": [],
                },
            )
        )

    assert store.query_events() == []


def test_sql_update_delete_and_public_mutation_methods_are_rejected(tmp_path: Path) -> None:
    store = _store(tmp_path)
    event = store.append_event(_draft())

    with pytest.raises(EventMutationError):
        store.update(event.event_id, payload={})
    with pytest.raises(EventMutationError):
        store.delete(event.event_id)
    with sqlite3.connect(tmp_path / "research.sqlite") as conn:
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            conn.execute("UPDATE research_events SET entity_id = 'x'")
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            conn.execute("DELETE FROM research_events")


def test_replay_rebuilds_identical_projection_state_hash_and_detects_tampering(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    store.append_event(_draft())
    store.append_event(
        _draft(
            event_type="TrialStarted",
            entity_id="trial-replay",
            payload={
                "trial_id": "trial-replay",
                "candidate_id": "candidate-replay",
                "data_scope": "train_valid",
                "objective": "rank_ic",
                "started_at": "2025-01-01T00:00:00Z",
            },
        )
    )
    store.append_event(
        _draft(
            event_type="EvaluationRecorded",
            entity_id="evaluation-1",
            payload={
                "evaluation_id": "evaluation-1",
                "trial_id": "trial-replay",
                "factor_spec_id": "factor-spec-1",
                "data_scope": "train_valid",
                "scorecard_hash": "sha256:" + "c" * 64,
                "artifact_refs": [],
                "metadata": {},
            },
        )
    )

    full = store.replay()
    repeated = store.replay()

    assert full == repeated
    assert full.event_count == 3
    assert full.watermark_event_hash == store.query_events()[-1].event_hash
    with sqlite3.connect(tmp_path / "research.sqlite") as conn:
        conn.execute("DROP TRIGGER research_events_no_update")
        conn.execute("UPDATE research_events SET payload = '{}' WHERE seq = 1")
    assert not store.verify_chain()
    with pytest.raises(ResearchEventAppendError, match="replay verification failed"):
        store.replay()


def test_writer_crash_rolls_back_partial_event_and_recovers(tmp_path: Path) -> None:
    class CrashingStore(ResearchEventStore):
        def _insert_event(self, conn, event, payload_json):  # noqa: ANN001
            super()._insert_event(conn, event, payload_json)
            raise RuntimeError("simulated writer crash")

    crashing = CrashingStore(
        tmp_path / "research.sqlite",
        artifact_root=tmp_path / "artifacts",
        flags=_flags(),
        code_version="test-code-v1",
    )

    with pytest.raises(ResearchEventAppendError, match="simulated writer crash"):
        crashing.append_event(_draft())

    recovered = _store(tmp_path)
    assert recovered.query_events() == []
    recovered.append_event(_draft())
    assert recovered.verify_chain()


def test_connection_lock_during_open_uses_bounded_retry_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _store(tmp_path)
    real_connect = store._connect
    attempts = 0

    def flaky_connect():  # noqa: ANN202
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise sqlite3.OperationalError("database is locked")
        return real_connect()

    monkeypatch.setattr(store, "_connect", flaky_connect)

    event = store.append_event(_draft())

    assert attempts == 3
    assert event.event_type == "FactorDefinitionRecorded"


def test_connection_retry_stops_at_configured_bound(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _store(tmp_path)
    store.max_retries = 3
    attempts = 0

    def always_locked():  # noqa: ANN202
        nonlocal attempts
        attempts += 1
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(store, "_connect", always_locked)

    with pytest.raises(ResearchEventAppendError, match="database is locked"):
        store.append_event(_draft())
    assert attempts == 3


def test_feature_off_store_refuses_before_creating_database_or_artifact_root(
    tmp_path: Path,
) -> None:
    with pytest.raises(RuntimeError, match="research events capability is disabled"):
        _store(tmp_path, enabled=False)

    assert list(tmp_path.iterdir()) == []


def test_durability_profiles_are_explicit_and_balanced_caps_research_only(
    tmp_path: Path,
) -> None:
    full = _store(tmp_path / "full")
    balanced = _store(tmp_path / "balanced", durability_profile="balanced")

    full_event = full.append_event(_draft())
    balanced_event = balanced.append_event(_draft())

    assert full.synchronous_mode == "FULL"
    assert full.decision_cap is None
    assert "REDUCED_DURABILITY" not in full_event.warnings
    assert balanced.synchronous_mode == "NORMAL"
    assert balanced.decision_cap == "research_only"
    assert "REDUCED_DURABILITY" in balanced_event.warnings
    assert full.durability_diagnostics() == {
        "journal_mode": "WAL",
        "synchronous": "FULL",
        "busy_timeout_ms": 30_000,
    }
    assert balanced.durability_diagnostics()["synchronous"] == "NORMAL"


def test_trial_ledger_v1_hash_contract_is_unchanged() -> None:
    entry = TrialLedgerEntry(
        trial_id="trial-golden",
        trial_group_id="group",
        parent_trial_id=None,
        candidate_id="candidate",
        parent_seed_id=None,
        formula="rank(close)",
        formula_hash="sha256:formula",
        data_snapshot_hash="sha256:snapshot",
        universe_hash="sha256:universe",
        split_id="train_valid",
        data_scope="train_valid",
        search_space_hash="sha256:space",
        objective="objective",
        random_seed=1,
        n_candidates_seen_so_far=1,
        status="success",
        decision="research_only",
        reason_codes=[],
        metrics_summary={"rank_ic": 0.01},
        previous_entry_hash=None,
        entry_hash="",
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc).isoformat(),
    )

    assert entry.with_hashes(None).entry_hash == (
        "sha256:0bd93ae1941ff5d8bcad66fdacca04ef5b04be0515d1d03362a50c0305bb8afd"
    )


def test_event_table_coexists_in_same_database_without_changing_v1_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "shared-research.sqlite"
    v1 = TrialLedger(db_path)
    entry = TrialLedgerEntry(
        trial_id="trial-v1-shared",
        trial_group_id="group",
        parent_trial_id=None,
        candidate_id="candidate",
        parent_seed_id=None,
        formula="rank(close)",
        formula_hash="sha256:formula",
        data_snapshot_hash="sha256:snapshot",
        universe_hash="sha256:universe",
        split_id="train_valid",
        data_scope="train_valid",
        search_space_hash="sha256:space",
        objective="objective",
        random_seed=1,
        n_candidates_seen_so_far=1,
        status="success",
        decision="research_only",
        reason_codes=[],
        metrics_summary={"rank_ic": 0.01},
        previous_entry_hash=None,
        entry_hash="",
        created_at="2025-01-01T00:00:00Z",
    )
    stored_v1 = v1.append(entry)
    events = ResearchEventStore(
        db_path,
        artifact_root=tmp_path / "artifacts",
        flags=_flags(),
        code_version="test-code-v1",
    )
    events.append_event(_draft())

    reread = TrialLedger(db_path).query()
    assert len(reread) == 1
    assert reread[0].to_dict() == stored_v1.to_dict()
    assert TrialLedger(db_path).verify_hash_chain()
    assert events.verify_chain()
