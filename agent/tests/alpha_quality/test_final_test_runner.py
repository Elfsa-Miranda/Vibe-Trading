from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.alpha_foundry.dsl.identity import FactorIdentityService, FactorSpecSemantics
from src.alpha_quality.decision_v2 import DecisionEvidenceRepository
from src.alpha_quality.final_test.model import (
    FinalTestDataRequest,
    FinalTestDataset,
    FinalTestPolicy,
    FrozenFinalCandidate,
)
from src.alpha_quality.final_test.runner import FinalTestRunner
from src.alpha_quality.flags import ResolvedAGSFlags
from src.alpha_quality.scope import TestScopeAuthority
from src.research_ledger.events import ResearchEventStore
from src.research_ledger.hash_utils import canonical_json_hash, utc_now_iso


def _flags(*, enabled: bool = True) -> ResolvedAGSFlags:
    return ResolvedAGSFlags.from_settings(
        {
            "VIBE_TRADING_AGS_ENABLED": "1",
            "VIBE_TRADING_RESEARCH_EVENTS": "1",
            "VIBE_TRADING_ALPHA_FOUNDRY": "1",
            "VIBE_TRADING_FACTOR_DAG": "1",
            "VIBE_TRADING_DECISION_V2": "1" if enabled else "0",
        }
    )


def _setup(tmp_path: Path):
    flags = _flags()
    store = ResearchEventStore(
        tmp_path / "research.sqlite",
        artifact_root=tmp_path / "artifacts",
        flags=flags,
        code_version="pr11-final-test",
    )
    digest = canonical_json_hash({"fixture": "final-runner"})
    attempt = FactorIdentityService(store=store, flags=flags).record_attempt(
        trial_id="trial-final-definition",
        run_id="final-run",
        candidate_id="candidate-final",
        formula="rank(close)",
        semantics=FactorSpecSemantics(
            transform_pipeline_hash=digest,
            field_semantics={"close": "pit_eod"},
            signal_time="close",
            order_time="next_open",
            entry_price_time="next_open",
            execution_lag=1,
            return_horizon=5,
            universe_mask_hash=digest,
            tradability_mask_hash=digest,
        ),
    )
    assert attempt.factor_spec_id is not None
    definition_event = store.query_events(
        event_type="FactorDefinitionRecorded", entity_id=attempt.factor_spec_id
    )[-1]
    policy = FinalTestPolicy(
        schema_version="final_test_policy.v1",
        policy_version="final-policy.1",
        minimum_effective_observations=4,
        minimum_rank_ic_mean=0.01,
        minimum_net_return_mean=0.0001,
    )
    candidate = FrozenFinalCandidate.create(
        factor_spec_id=attempt.factor_spec_id,
        definition_hash=definition_event.event_hash,
        transform_pipeline_hash=digest,
        cost_model_hash=digest,
        regime_config_hash=digest,
        policy_hash=policy.policy_hash,
        data_snapshot_hash=digest,
        frozen_at=utc_now_iso(),
    )
    authority = TestScopeAuthority(store=store, flags=flags)
    capability = authority.issue(
        candidate,
        run_id="final-run",
        period_start="2025-01-01",
        period_end="2025-03-31",
    )
    request = FinalTestDataRequest(
        run_id="final-run",
        factor_spec_id=candidate.factor_spec_id,
        candidate_hash=candidate.candidate_hash,
        data_snapshot_hash=candidate.data_snapshot_hash,
        period_start="2025-01-01",
        period_end="2025-03-31",
        fields=("net_returns", "rank_ic_series"),
    )
    return flags, store, policy, candidate, authority, capability, request


class _Provider:
    def __init__(self, *, mismatched: bool = False) -> None:
        self.mismatched = mismatched
        self.calls = 0

    def load_final(self, request: FinalTestDataRequest) -> FinalTestDataset:
        self.calls += 1
        snapshot = (
            canonical_json_hash({"wrong": "snapshot"})
            if self.mismatched
            else request.data_snapshot_hash
        )
        return FinalTestDataset(
            data_snapshot_hash=snapshot,
            period_start=request.period_start,
            period_end=request.period_end,
            rank_ic_series=(0.02, 0.03, 0.04, 0.05),
            net_returns=(0.001, 0.002, 0.003, 0.004),
            limitations=("EOD_PROXY_LIMITATION",),
        )


def test_final_artifact_contains_no_raw_panel_or_absolute_path(tmp_path: Path) -> None:
    flags, store, policy, candidate, authority, capability, request = _setup(tmp_path)
    runner = FinalTestRunner(
        flags=flags,
        authority=authority,
        provider=_Provider(),
        policy=policy,
        store=store,
    )
    artifact = runner.run(candidate, capability, request, run_id="final-run")
    payload = artifact.to_dict()
    encoded = json.dumps(payload, sort_keys=True)

    assert artifact.quality_passed
    assert "rank_ic_series" not in payload
    assert "net_returns" not in payload
    assert "D:\\" not in encoded and "/home/" not in encoded
    assert set(payload) >= {
        "rank_ic_mean",
        "rank_ic_standard_error",
        "net_return_mean",
        "net_return_standard_error",
        "access_audit",
    }
    assert store.verify_chain()


def test_provider_scope_mismatch_is_audited_and_cannot_create_artifact(
    tmp_path: Path,
) -> None:
    flags, store, policy, candidate, authority, capability, request = _setup(tmp_path)
    runner = FinalTestRunner(
        flags=flags,
        authority=authority,
        provider=_Provider(mismatched=True),
        policy=policy,
        store=store,
    )

    with pytest.raises(ValueError, match="mismatched frozen data scope"):
        runner.run(candidate, capability, request, run_id="final-run")

    assert authority.is_tainted(candidate.candidate_hash)
    assert not store.query_events(event_type="FinalTestArtifactRecorded")
    assert store.query_events(event_type="FinalTestAccessRecorded")[-1].hard_failures == (
        "FINAL_TEST_CONTAMINATED",
    )


def test_final_decision_view_is_the_only_repository_adapter(tmp_path: Path) -> None:
    flags, store, policy, candidate, authority, capability, request = _setup(tmp_path)
    runner = FinalTestRunner(
        flags=flags,
        authority=authority,
        provider=_Provider(),
        policy=policy,
        store=store,
    )
    artifact = runner.run(candidate, capability, request, run_id="final-run")
    repository = DecisionEvidenceRepository(tmp_path / "decision-evidence")
    with pytest.raises(TypeError, match="DecisionEvidenceRecord"):
        repository.put(artifact)  # type: ignore[arg-type]
    evidence_hash = runner.record_decision_evidence(artifact, repository)
    record = repository.resolve(
        evidence_hash,
        expected_kind="final_test",
        factor_spec_id=candidate.factor_spec_id,
    )

    assert record.payload["frozen"] is True
    assert record.payload["one_shot"] is True
    assert record.payload["contaminated"] is False
    assert "rank_ic_series" not in record.payload


def test_final_runner_feature_off_creates_no_access_or_artifact(tmp_path: Path) -> None:
    flags, store, policy, _, authority, _, _ = _setup(tmp_path)
    before = len(store.query_events())
    with pytest.raises(RuntimeError, match="disabled"):
        FinalTestRunner(
            flags=_flags(enabled=False),
            authority=authority,
            provider=_Provider(),
            policy=policy,
            store=store,
        )
    assert len(store.query_events()) == before


def test_final_dataset_rejects_path_secret_and_nonfinite_metadata() -> None:
    digest = canonical_json_hash({"fixture": "safe"})
    with pytest.raises(ValueError, match="safe codes"):
        FinalTestDataset(
            data_snapshot_hash=digest,
            period_start="2025-01-01",
            period_end="2025-01-31",
            rank_ic_series=(0.01, 0.02),
            net_returns=(0.001, 0.002),
            limitations=("D:\\private\\panel.parquet",),
        )
    with pytest.raises(ValueError, match="non-finite"):
        FinalTestDataset(
            data_snapshot_hash=digest,
            period_start="2025-01-01",
            period_end="2025-01-31",
            rank_ic_series=(0.01, float("nan")),
            net_returns=(0.001, 0.002),
        )
