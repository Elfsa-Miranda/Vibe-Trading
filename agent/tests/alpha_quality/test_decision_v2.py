from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.alpha_quality.decision_v2 import (
    DecisionEvidenceRecord,
    DecisionEvidenceRefs,
    DecisionEvidenceRepository,
    DecisionV2Policy,
    EvidenceResolutionError,
    QualityDecisionV2Runner,
    QualityDecisionV2Service,
)
from src.alpha_quality.flags import ResolvedAGSFlags
from src.research_ledger.events import EventDraft, ResearchEventStore
from src.research_ledger.hash_utils import canonical_json_hash


def _flags(*, enabled: bool = True, events: bool = False) -> ResolvedAGSFlags:
    return ResolvedAGSFlags.from_settings(
        {
            "VIBE_TRADING_AGS_ENABLED": "1",
            "VIBE_TRADING_DECISION_V2": "1" if enabled else "0",
            "VIBE_TRADING_RESEARCH_EVENTS": "1" if events else "0",
        }
    )


def _policy() -> DecisionV2Policy:
    return DecisionV2Policy(
        schema_version="decision_v2_policy.v1",
        policy_version="decision-v2-policy.1",
    )


def _defaults(kind: str) -> dict[str, object]:
    return {
        "scorecard": {
            "formula_valid": True,
            "formula_ambiguous": False,
            "lookahead_detected": False,
            "train_valid_terminal": True,
            "reproducible": True,
            "bounded": True,
            "validation_rank_ic": 0.04,
            "regime_dependent": False,
            "limitations": ["TRAIN_VALID_ONLY"],
        },
        "execution": {
            "available": True,
            "execution_alpha": 0.002,
            "total_cost": 0.0005,
            "economically_nonnegative": True,
            "limitations": [],
        },
        "snapshot": {
            "pit_available": True,
            "survivorship_bias": False,
            "limitations": [],
        },
        "ledger": {
            "complete": True,
            "terminal_train_valid": True,
            "reduced_durability": False,
            "limitations": [],
        },
        "mechanism": {
            "contract_registered": True,
            "decisive_available": True,
            "ordinal_state": "partial_support",
            "limitations": ["ORDINAL_NOT_PROBABILITY"],
        },
        "complement": {
            "status": "complementary",
            "limitations": ["TRAIN_VALID_ONLY"],
        },
        "final_test": {
            "source_artifact_hash": canonical_json_hash({"final": "artifact"}),
            "view_hash": canonical_json_hash({"final": "view"}),
            "frozen": True,
            "one_shot": True,
            "contaminated": False,
            "quality_passed": True,
            "final_oos_ic": 0.03,
            "limitations": ["ONE_SHOT_FINAL"],
        },
        "forward_plan": {
            "plan_hash": canonical_json_hash({"forward": "plan"}),
            "frozen": True,
            "minimum_observations": 20,
            "success_claim": False,
            "limitations": ["TRACKING_STARTED_NOT_SUCCESS"],
        },
    }[kind]


def _put(
    repository: DecisionEvidenceRepository,
    kind: str,
    **changes: object,
) -> str:
    payload = _defaults(kind)
    payload.update(changes)
    record = DecisionEvidenceRecord.create(
        evidence_kind=kind,  # type: ignore[arg-type]
        factor_spec_id="factor-1",
        payload=payload,
    )
    return repository.put(record)


def _refs(
    repository: DecisionEvidenceRepository,
    *,
    scorecard: dict[str, object] | None = None,
    execution: dict[str, object] | None = None,
    snapshot: dict[str, object] | None = None,
    ledger: dict[str, object] | None = None,
    mechanism: dict[str, object] | None = None,
    complement: dict[str, object] | None = None,
    final_test: dict[str, object] | None = None,
    forward_plan: dict[str, object] | None = None,
    omit: set[str] | None = None,
) -> DecisionEvidenceRefs:
    omitted = omit or set()

    def stored(kind: str, changes: dict[str, object] | None) -> str | None:
        if kind in omitted:
            return None
        return _put(repository, kind, **(changes or {}))

    scorecard_hash = stored("scorecard", scorecard)
    ledger_hash = stored("ledger", ledger)
    assert scorecard_hash is not None and ledger_hash is not None
    return DecisionEvidenceRefs(
        factor_spec_id="factor-1",
        scorecard_hash=scorecard_hash,
        execution_hash=stored("execution", execution),
        snapshot_hash=stored("snapshot", snapshot),
        ledger_watermark_hash=ledger_hash,
        mechanism_evidence_hash=stored("mechanism", mechanism),
        complement_evidence_hash=stored("complement", complement),
        final_test_artifact_hash=stored("final_test", final_test) if final_test is not None else None,
        forward_plan_hash=stored("forward_plan", forward_plan) if forward_plan is not None else None,
    )


def _runner(repository: DecisionEvidenceRepository) -> QualityDecisionV2Runner:
    return QualityDecisionV2Runner(flags=_flags(), policy=_policy(), repository=repository)


def test_soft_score_cannot_cross_hard_cap(tmp_path: Path) -> None:
    repository = DecisionEvidenceRepository(tmp_path / "evidence")
    refs = _refs(
        repository,
        scorecard={"validation_rank_ic": 999.0},
        snapshot={"pit_available": False},
    )

    result = _runner(repository).run(refs)

    assert result.within_tier_score <= 1.0
    assert result.decision == "research_only"
    assert "PIT_SNAPSHOT_MISSING" in result.caps


def test_caller_cannot_supply_decision_failures_caps_or_total_score() -> None:
    digest = canonical_json_hash({"fixture": "hash"})
    base = {
        "factor_spec_id": "factor-1",
        "scorecard_hash": digest,
        "execution_hash": None,
        "snapshot_hash": None,
        "ledger_watermark_hash": digest,
        "mechanism_evidence_hash": None,
        "complement_evidence_hash": None,
        "final_test_artifact_hash": None,
        "forward_plan_hash": None,
    }
    for forbidden in ("decision", "hard_failures", "warnings", "caps", "total_quality_score"):
        with pytest.raises(ValueError, match="forbidden"):
            DecisionEvidenceRefs.from_mapping({**base, forbidden: "caller truth"})


def test_invalid_formula_is_rejected_before_scorecard(tmp_path: Path) -> None:
    repository = DecisionEvidenceRepository(tmp_path / "evidence")
    result = _runner(repository).run(
        _refs(repository, scorecard={"formula_valid": False, "validation_rank_ic": 99.0})
    )

    assert result.decision == "reject"
    assert "INVALID_FORMULA" in result.reasons


def test_missing_execution_is_cap_but_explicit_cost_exceeds_alpha_can_reject(
    tmp_path: Path,
) -> None:
    missing_repository = DecisionEvidenceRepository(tmp_path / "missing")
    missing = _runner(missing_repository).run(
        _refs(missing_repository, omit={"execution"})
    )
    costly_repository = DecisionEvidenceRepository(tmp_path / "costly")
    costly = _runner(costly_repository).run(
        _refs(costly_repository, execution={"execution_alpha": 0.001, "total_cost": 0.002})
    )

    assert missing.decision == "research_only"
    assert "EXECUTION_EVIDENCE_MISSING" in missing.caps
    assert costly.decision == "reject"
    assert "COST_EXCEEDS_EXECUTION_ALPHA" in costly.reasons


def test_missing_contract_or_complement_does_not_fail_open(tmp_path: Path) -> None:
    for missing in ({"mechanism"}, {"complement"}):
        repository = DecisionEvidenceRepository(tmp_path / next(iter(missing)))
        result = _runner(repository).run(_refs(repository, omit=missing))
        assert result.decision == "research_only"
        assert result.caps


def test_final_oos_ic_alone_cannot_create_paper_candidate(tmp_path: Path) -> None:
    repository = DecisionEvidenceRepository(tmp_path / "evidence")
    result = _runner(repository).run(
        _refs(repository, final_test={"quality_passed": False, "final_oos_ic": 999.0})
    )

    assert result.decision == "candidate_zoo"
    assert "FINAL_TEST_DID_NOT_PASS_FROZEN_QUALITY" in result.warnings


def test_final_scope_contamination_is_a_noncompensatory_reject(tmp_path: Path) -> None:
    repository = DecisionEvidenceRepository(tmp_path / "evidence")
    result = _runner(repository).run(
        _refs(
            repository,
            scorecard={"validation_rank_ic": 999.0},
            final_test={"contaminated": True, "quality_passed": False},
        )
    )

    assert result.decision == "reject"
    assert "FINAL_TEST_CONTAMINATED" in result.reasons


def test_regime_dependence_is_metadata_not_new_decision_level(tmp_path: Path) -> None:
    repository = DecisionEvidenceRepository(tmp_path / "evidence")
    result = _runner(repository).run(
        _refs(repository, scorecard={"regime_dependent": True})
    )

    assert result.decision == "candidate_zoo"
    assert "REGIME_DEPENDENT" in result.warnings


def test_candidate_zoo_does_not_require_final_test(tmp_path: Path) -> None:
    repository = DecisionEvidenceRepository(tmp_path / "evidence")
    result = _runner(repository).run(_refs(repository))

    assert result.decision == "candidate_zoo"
    assert result.tier == 2


def test_paper_candidate_requires_one_valid_frozen_final_artifact(tmp_path: Path) -> None:
    repository = DecisionEvidenceRepository(tmp_path / "evidence")
    valid = _runner(repository).run(_refs(repository, final_test={}))
    invalid_repository = DecisionEvidenceRepository(tmp_path / "invalid")
    invalid = _runner(invalid_repository).run(
        _refs(invalid_repository, final_test={"one_shot": False})
    )

    assert valid.decision == "paper_candidate"
    assert invalid.decision == "candidate_zoo"


def test_forward_track_requires_frozen_plan_and_does_not_claim_success(
    tmp_path: Path,
) -> None:
    repository = DecisionEvidenceRepository(tmp_path / "evidence")
    tracked = _runner(repository).run(
        _refs(repository, final_test={}, forward_plan={})
    )
    unfrozen_repository = DecisionEvidenceRepository(tmp_path / "unfrozen")
    unfrozen = _runner(unfrozen_repository).run(
        _refs(unfrozen_repository, final_test={}, forward_plan={"frozen": False})
    )

    assert tracked.decision == "forward_track"
    assert tracked.forward_success_claim is False
    assert "FORWARD_TRACKING_STARTED_NO_SUCCESS_CLAIM" in tracked.warnings
    assert unfrozen.decision == "paper_candidate"


def test_decision_replay_from_evidence_hashes_is_identical(tmp_path: Path) -> None:
    repository = DecisionEvidenceRepository(tmp_path / "evidence")
    refs = _refs(repository, final_test={}, forward_plan={})
    runner = _runner(repository)

    first = runner.run(refs)
    second = runner.run(DecisionEvidenceRefs.from_mapping(refs.to_dict()))

    assert first == second
    assert first.decision_hash == second.decision_hash


def test_evidence_repository_rejects_tampering_and_wrong_factor(tmp_path: Path) -> None:
    repository = DecisionEvidenceRepository(tmp_path / "evidence")
    evidence_hash = _put(repository, "scorecard")
    path = repository.root / (evidence_hash.removeprefix("sha256:") + ".json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["payload"]["validation_rank_ic"] = 1.0
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(EvidenceResolutionError, match="tampered"):
        repository.resolve(evidence_hash, expected_kind="scorecard", factor_spec_id="factor-1")


def test_decision_service_records_event_and_feature_off_is_no_write(tmp_path: Path) -> None:
    flags = _flags(events=True)
    store = ResearchEventStore(
        tmp_path / "research.sqlite",
        artifact_root=tmp_path / "artifacts",
        flags=flags,
        code_version="pr10-test",
    )
    digest = canonical_json_hash({"fixture": "definition"})
    store.append_event(
        EventDraft(
            event_type="FactorDefinitionRecorded",
            entity_id="factor-1",
            run_id="run-decision",
            payload_schema_version="factor_definition_recorded.v1",
            payload={
                "factor_spec_id": "factor-1",
                "expression_id": "expression-1",
                "canonical_ast_hash": digest,
                "grammar_version": "1.0.0",
                "grammar_hash": digest,
                "metadata": {},
                "artifact_refs": [],
            },
        )
    )
    repository = DecisionEvidenceRepository(tmp_path / "evidence")
    service = QualityDecisionV2Service(
        store=store,
        flags=flags,
        policy=_policy(),
        repository=repository,
    )
    refs = _refs(repository)

    first = service.decide_and_record(refs, run_id="run-decision")
    retried = service.decide_and_record(refs, run_id="run-decision")

    assert first.event == retried.event
    assert first.event.payload["decision"] == "candidate_zoo"
    assert store.verify_chain()
    assert store.replay().event_count == 2
    before = len(store.query_events())
    with pytest.raises(RuntimeError, match="disabled"):
        QualityDecisionV2Service(
            store=store,
            flags=_flags(enabled=False, events=True),
            policy=_policy(),
            repository=repository,
        )
    assert len(store.query_events()) == before
