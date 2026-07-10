from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.alpha_quality.complement import (
    ComplementEngine,
    ComplementEvidenceService,
    ComplementInputs,
    ComplementPolicy,
    FactorIdentityRecord,
    build_duplicate_identity_evidence,
    compute_portfolio_complement,
    compute_residual_complement,
)
from src.alpha_quality.flags import ResolvedAGSFlags
from src.research_ledger.events import EventDraft, ResearchEventStore
from src.research_ledger.hash_utils import canonical_json_hash


def _hash(label: object) -> str:
    return canonical_json_hash({"fixture": label})


def _flags(*, enabled: bool = True) -> ResolvedAGSFlags:
    return ResolvedAGSFlags.from_settings(
        {
            "VIBE_TRADING_AGS_ENABLED": "1" if enabled else "0",
            "VIBE_TRADING_COMPLEMENT_V2": "1",
        }
    )


def _service_flags(*, complement_enabled: bool = True) -> ResolvedAGSFlags:
    return ResolvedAGSFlags.from_settings(
        {
            "VIBE_TRADING_AGS_ENABLED": "1",
            "VIBE_TRADING_RESEARCH_EVENTS": "1",
            "VIBE_TRADING_COMPLEMENT_V2": "1" if complement_enabled else "0",
        }
    )


def _policy(**changes: object) -> ComplementPolicy:
    values: dict[str, object] = {
        "schema_version": "complement_policy.v2",
        "policy_version": "complement-policy.v2",
        "data_scope": "valid",
        "panel_duplicate_threshold": 0.95,
        "ic_duplicate_threshold": 0.95,
        "return_duplicate_threshold": 0.95,
        "ridge_alpha": 0.1,
        "minimum_cross_section": 6,
        "minimum_effective_dates": 8,
        "candidate_allocation": 0.25,
        "annualization_factor": 252,
        "bootstrap_samples": 64,
        "bootstrap_block_length": 3,
        "bootstrap_seed": 17,
        "require_execution_evidence": True,
        "require_capacity_evidence": True,
        "require_exposure_evidence": True,
        "portfolio_construction_hash": _hash("construction"),
        "cost_model_hash": _hash("cost"),
        "capacity_model_hash": _hash("capacity"),
        "exposure_model_hash": _hash("exposure"),
    }
    values.update(changes)
    return ComplementPolicy(**values)  # type: ignore[arg-type]


def _identity(label: str, *, sign_group: str | None = None) -> FactorIdentityRecord:
    return FactorIdentityRecord(
        factor_spec_id=f"factor-{label}",
        expression_id=_hash(("expression", label)),
        formula_hash=_hash(("formula", label)),
        sign_normalized_id=_hash(("sign", sign_group or label)),
    )


def _panels() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(20260711)
    dates = pd.date_range("2024-01-01", periods=12, freq="D")
    symbols = [f"S{index:02d}" for index in range(10)]
    reference_values = rng.normal(size=(len(dates), len(symbols)))
    orthogonal_values = rng.normal(size=(len(dates), len(symbols)))
    reference = pd.DataFrame(reference_values, index=dates, columns=symbols)
    collinear = 2.0 * reference
    candidate = pd.DataFrame(
        0.2 * reference_values + orthogonal_values,
        index=dates,
        columns=symbols,
    )
    forward = pd.DataFrame(
        orthogonal_values + 0.05 * rng.normal(size=orthogonal_values.shape),
        index=dates,
        columns=symbols,
    )
    return candidate, reference, collinear, forward


def _complete_inputs(**changes: object) -> ComplementInputs:
    candidate, reference, collinear, forward = _panels()
    dates = candidate.index
    candidate_returns = pd.Series(
        0.002 + 0.001 * np.sin(np.arange(len(dates))), index=dates
    )
    existing_returns = pd.Series(
        0.0002 * np.cos(np.arange(len(dates)) * 1.7), index=dates
    )
    values: dict[str, object] = {
        "snapshot_hash": _hash("snapshot"),
        "candidate_identity": _identity("candidate"),
        "existing_identities": (_identity("reference"), _identity("collinear")),
        "candidate_panel": candidate,
        "existing_panels": {"factor-reference": reference, "factor-collinear": collinear},
        "candidate_ic_series": pd.Series(np.linspace(-0.2, 0.3, len(dates)), index=dates),
        "existing_ic_series": {
            "factor-reference": pd.Series(np.cos(np.arange(len(dates))), index=dates),
            "factor-collinear": pd.Series(np.sin(np.arange(len(dates)) * 1.3), index=dates),
        },
        "candidate_net_returns": candidate_returns - 0.0001,
        "existing_net_returns": {
            "factor-reference": existing_returns,
            "factor-collinear": -existing_returns.shift(1).fillna(0.0),
        },
        "forward_returns": forward,
        "valid_mask": pd.DataFrame(True, index=candidate.index, columns=candidate.columns),
        "pool_net_returns": existing_returns,
        "candidate_gross_returns": candidate_returns,
        "pool_turnover": pd.Series(0.05, index=dates),
        "candidate_turnover": pd.Series(0.10, index=dates),
        "candidate_cost_bps": pd.Series(2.0, index=dates),
        "candidate_capacity_scale": pd.Series(0.90, index=dates),
        "candidate_exposure_penalty": pd.Series(0.00002, index=dates),
        "semantic_similarity": None,
        "structural_similarity": None,
        "polarity_control": False,
    }
    values.update(changes)
    return ComplementInputs(**values)  # type: ignore[arg-type]


def _source_events(
    store: ResearchEventStore,
    *,
    factor_spec_id: str = "factor-candidate",
    data_scope: str = "valid",
) -> tuple[str, str]:
    digest = _hash("event-fixture")
    store.append_event(
        EventDraft(
            event_type="FactorDefinitionRecorded",
            entity_id=factor_spec_id,
            run_id="run-complement",
            payload_schema_version="factor_definition_recorded.v1",
            payload={
                "factor_spec_id": factor_spec_id,
                "expression_id": "expression-candidate",
                "canonical_ast_hash": digest,
                "grammar_version": "1.0.0",
                "grammar_hash": digest,
                "metadata": {},
                "artifact_refs": [],
            },
        )
    )
    store.append_event(
        EventDraft(
            event_type="TrialStarted",
            entity_id="trial-complement",
            run_id="run-complement",
            payload_schema_version="trial_started.v1",
            payload={
                "trial_id": "trial-complement",
                "candidate_id": factor_spec_id,
                "data_scope": data_scope,
                "objective": "complement_v2",
                "started_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    )
    evaluation = store.append_event(
        EventDraft(
            event_type="EvaluationRecorded",
            entity_id="evaluation-complement",
            run_id="run-complement",
            payload_schema_version="evaluation_recorded.v1",
            payload={
                "evaluation_id": "evaluation-complement",
                "trial_id": "trial-complement",
                "factor_spec_id": factor_spec_id,
                "data_scope": data_scope,
                "scorecard_hash": digest,
                "artifact_refs": [],
                "metadata": {},
            },
        )
    )
    terminal = store.append_event(
        EventDraft(
            event_type="TrialTerminated",
            entity_id="trial-complement",
            run_id="run-complement",
            payload_schema_version="trial_terminated.v1",
            payload={
                "trial_id": "trial-complement",
                "status": "success",
                "reason_codes": [],
                "decision": "candidate_zoo",
                "evaluation_event_hash": evaluation.event_hash,
                "terminated_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    )
    return evaluation.event_hash, terminal.event_hash


def test_sign_flipped_duplicate_is_detected_by_absolute_correlations() -> None:
    candidate, reference, _, _ = _panels()
    dates = candidate.index
    candidate_identity = _identity("negative", sign_group="shared")
    reference_identity = _identity("positive", sign_group="shared")
    evidence = build_duplicate_identity_evidence(
        candidate_identity,
        (reference_identity,),
        candidate_panel=-reference,
        existing_panels={reference_identity.factor_spec_id: reference},
        candidate_ic_series=-pd.Series(np.arange(len(dates), dtype=float), index=dates),
        existing_ic_series={
            reference_identity.factor_spec_id: pd.Series(np.arange(len(dates), dtype=float), index=dates)
        },
        candidate_net_returns=-pd.Series(np.arange(len(dates), dtype=float), index=dates),
        existing_net_returns={
            reference_identity.factor_spec_id: pd.Series(np.arange(len(dates), dtype=float), index=dates)
        },
        policy=_policy(),
    )

    assert evidence.duplicate_detected
    assert "SIGN_NORMALIZED_DUPLICATE" in evidence.duplicate_reasons
    assert evidence.panel_correlation.maximum_absolute_correlation == pytest.approx(1.0)
    assert evidence.ic_correlation.maximum_absolute_correlation == pytest.approx(1.0)
    assert evidence.return_correlation.maximum_absolute_correlation == pytest.approx(1.0)


def test_formula_output_ic_and_return_identity_are_reported_separately() -> None:
    candidate, reference, _, _ = _panels()
    dates = candidate.index
    candidate_identity = _identity("candidate")
    reference_identity = replace(
        _identity("reference"),
        expression_id=candidate_identity.expression_id,
    )
    evidence = build_duplicate_identity_evidence(
        candidate_identity,
        (reference_identity,),
        candidate_panel=candidate,
        existing_panels={reference_identity.factor_spec_id: reference},
        candidate_ic_series=pd.Series(np.arange(len(dates)), index=dates),
        existing_ic_series={reference_identity.factor_spec_id: pd.Series(np.arange(len(dates)), index=dates)},
        candidate_net_returns=pd.Series(np.sin(np.arange(len(dates))), index=dates),
        existing_net_returns={reference_identity.factor_spec_id: pd.Series(np.cos(np.arange(len(dates))), index=dates)},
        policy=_policy(),
    )

    assert evidence.exact_expression_matches == (reference_identity.factor_spec_id,)
    assert evidence.exact_factor_spec_matches == ()
    assert evidence.exact_formula_matches == ()
    assert evidence.panel_correlation.dimension == "factor_panel_rank"
    assert evidence.ic_correlation.dimension == "ic_series"
    assert evidence.return_correlation.dimension == "net_return"


def test_residualization_is_date_aligned_and_uses_ridge_fallback() -> None:
    candidate, reference, collinear, forward = _panels()
    evidence = compute_residual_complement(
        candidate_panel=candidate,
        reference_panels={"factor-a": reference, "factor-collinear": collinear},
        forward_returns=forward,
        valid_mask=pd.DataFrame(True, index=candidate.index, columns=candidate.columns),
        policy=_policy(),
    )

    assert evidence.availability == "available"
    assert evidence.solver == "date_wise_ridge"
    assert evidence.effective_dates == len(candidate.index)
    assert evidence.rank_ic_mean is not None and evidence.rank_ic_mean > 0.7
    assert evidence.uncertainty_method == "standard"


def test_marginal_portfolio_value_is_net_of_cost_and_capacity() -> None:
    inputs = _complete_inputs()
    evidence = compute_portfolio_complement(
        pool_net_returns=inputs.pool_net_returns,
        candidate_gross_returns=inputs.candidate_gross_returns,
        pool_turnover=inputs.pool_turnover,
        candidate_turnover=inputs.candidate_turnover,
        candidate_cost_bps=inputs.candidate_cost_bps,
        candidate_capacity_scale=inputs.candidate_capacity_scale,
        candidate_exposure_penalty=inputs.candidate_exposure_penalty,
        policy=_policy(),
    )

    assert evidence.availability == "available"
    assert evidence.candidate_cost_bps_mean == pytest.approx(2.0)
    assert evidence.candidate_capacity_scale_mean == pytest.approx(0.9)
    assert evidence.candidate_exposure_penalty_mean == pytest.approx(0.00002)
    assert evidence.delta_net_return_mean is not None and evidence.delta_net_return_mean > 0.0
    assert evidence.delta_ir_interval is not None


def test_redundant_high_ic_factor_has_nonpositive_marginal_value_fixture() -> None:
    inputs = _complete_inputs()
    assert inputs.candidate_panel is not None
    reference = next(iter(inputs.existing_panels.values()))  # type: ignore[union-attr]
    dates = inputs.candidate_panel.index
    redundant = replace(
        inputs,
        candidate_identity=_identity("duplicate", sign_group="reference"),
        existing_identities=(_identity("reference", sign_group="reference"),),
        candidate_panel=reference,
        existing_panels={"factor-reference": reference},
        candidate_ic_series=pd.Series(np.linspace(0.5, 0.9, len(dates)), index=dates),
        existing_ic_series={"factor-reference": pd.Series(np.linspace(0.5, 0.9, len(dates)), index=dates)},
        candidate_net_returns=inputs.pool_net_returns,
        existing_net_returns={"factor-reference": inputs.pool_net_returns},
        candidate_gross_returns=pd.Series(-0.002, index=dates),
    )
    result = ComplementEngine(flags=_flags(), policy=_policy()).evaluate(redundant)

    assert result.status == "duplicate"
    assert result.identity.duplicate_detected
    assert result.portfolio.delta_net_return_mean is not None
    assert result.portfolio.delta_net_return_mean < 0.0


def test_weaker_orthogonal_factor_can_have_positive_marginal_value() -> None:
    result = ComplementEngine(flags=_flags(), policy=_policy()).evaluate(_complete_inputs())

    assert result.status == "complementary"
    assert not result.identity.duplicate_detected
    assert result.residual.rank_ic_mean is not None and result.residual.rank_ic_mean > 0.0
    assert result.portfolio.delta_information_ratio is not None
    assert result.portfolio.delta_information_ratio > 0.0


def test_missing_complement_or_execution_evidence_does_not_fail_open() -> None:
    missing_execution = _complete_inputs(candidate_cost_bps=None)
    result = ComplementEngine(flags=_flags(), policy=_policy()).evaluate(missing_execution)

    assert result.status == "unavailable"
    assert result.cap == "RESEARCH_ONLY"
    assert result.portfolio.availability == "unavailable"
    assert result.portfolio.delta_information_ratio is None
    assert "COMPLEMENT_REQUIRED_EVIDENCE_UNAVAILABLE" in result.reason_codes


def test_probe_leaf_likelihood_is_not_an_admission_gate() -> None:
    baseline = ComplementEngine(flags=_flags(), policy=_policy()).evaluate(_complete_inputs())
    advisory = ComplementEngine(flags=_flags(), policy=_policy()).evaluate(
        _complete_inputs(semantic_similarity=1.0, structural_similarity=1.0)
    )

    assert baseline.status == advisory.status == "complementary"
    assert "SEMANTIC_SIMILARITY_ADVISORY_ONLY" in advisory.warning_codes
    assert "STRUCTURAL_SIMILARITY_ADVISORY_ONLY" in advisory.warning_codes


def test_complement_v2_feature_off_refuses_before_computation() -> None:
    with pytest.raises(RuntimeError, match="disabled"):
        ComplementEngine(flags=_flags(enabled=False), policy=_policy())


def test_complement_service_persists_content_addressed_event_and_replays(
    tmp_path: Path,
) -> None:
    flags = _service_flags()
    store = ResearchEventStore(
        tmp_path / "research.sqlite",
        artifact_root=tmp_path / "artifacts",
        flags=flags,
        code_version="pr9-test",
    )
    evaluation_hash, terminal_hash = _source_events(store)
    service = ComplementEvidenceService(store=store, flags=flags, policy=_policy())

    first = service.evaluate_and_record(
        _complete_inputs(),
        source_evaluation_event_hash=evaluation_hash,
        source_terminal_event_hash=terminal_hash,
        run_id="run-complement",
    )
    retried = service.evaluate_and_record(
        _complete_inputs(),
        source_evaluation_event_hash=evaluation_hash,
        source_terminal_event_hash=terminal_hash,
        run_id="run-complement",
    )

    assert first.event == retried.event
    assert first.event.payload["complement_hash"] == first.evidence.complement_hash
    assert first.event.payload["status"] == "complementary"
    assert first.event.payload["source_evaluation_event_hash"] == evaluation_hash
    assert first.event.payload["source_terminal_event_hash"] == terminal_hash
    artifact = tmp_path / "artifacts" / first.artifact_reference["relative_path"]
    assert artifact.is_file()
    assert store.verify_chain()
    assert store.replay().event_count == len(store.query_events())


def test_complement_service_rejects_scope_mismatch_before_artifact_write(
    tmp_path: Path,
) -> None:
    flags = _service_flags()
    store = ResearchEventStore(
        tmp_path / "research.sqlite",
        artifact_root=tmp_path / "artifacts",
        flags=flags,
        code_version="pr9-test",
    )
    evaluation_hash, terminal_hash = _source_events(store, data_scope="train")
    service = ComplementEvidenceService(store=store, flags=flags, policy=_policy())

    with pytest.raises(ValueError, match="frozen scope"):
        service.evaluate_and_record(
            _complete_inputs(),
            source_evaluation_event_hash=evaluation_hash,
            source_terminal_event_hash=terminal_hash,
            run_id="run-complement",
        )

    assert not (tmp_path / "artifacts" / "complement_v2").exists()
    assert not store.query_events(event_type="ComplementEvidenceRecorded")


def test_complement_service_feature_off_creates_no_artifact_or_event(
    tmp_path: Path,
) -> None:
    store_flags = _service_flags()
    store = ResearchEventStore(
        tmp_path / "research.sqlite",
        artifact_root=tmp_path / "artifacts",
        flags=store_flags,
        code_version="pr9-test",
    )
    before = len(store.query_events())

    with pytest.raises(RuntimeError, match="disabled"):
        ComplementEvidenceService(
            store=store,
            flags=_service_flags(complement_enabled=False),
            policy=_policy(),
        )

    assert len(store.query_events()) == before
    assert not (tmp_path / "artifacts" / "complement_v2").exists()
