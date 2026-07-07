from __future__ import annotations

from datetime import datetime, timezone

from src.alpha_foundry.overfit.multiple_testing import build_multiple_testing_report
from src.alpha_foundry.overfit.trial_ledger import TrialLedger, TrialRecord
from src.alpha_foundry.overfit.trial_matrix import build_trial_family_matrix


def _record(
    trial_id: str,
    *,
    family_id: str = "residual_price_volume_behavior",
    sub_family_id: str = "residual_20d_momentum",
    outcome: str = "reported",
) -> TrialRecord:
    return TrialRecord(
        trial_id=trial_id,
        family_id=family_id,
        sub_family_id=sub_family_id,
        hypothesis_id=sub_family_id,
        factor_id=sub_family_id,
        factor_definition_hash="factor-hash",
        parameter_variant={"trial": trial_id},
        param_hash=f"param-{trial_id}",
        started_at=datetime(2026, 1, 5, tzinfo=timezone.utc),
        completed_at=datetime(2026, 1, 5, 1, tzinfo=timezone.utc),
        outcome=outcome,  # type: ignore[arg-type]
        report_ref=f"report-{trial_id}",
    )


def _ledger() -> TrialLedger:
    ledger = TrialLedger.create(
        ledger_id="ledger-residual",
        family_id="residual_price_volume_behavior",
    )
    ledger = ledger.append(_record("trial-a", outcome="selected"))
    ledger = ledger.append(_record("trial-b", outcome="rejected"))
    ledger = ledger.append(_record("trial-c", outcome="abandoned"))
    ledger = ledger.append(
        _record(
            "trial-d",
            sub_family_id="abnormal_turnover_unwind",
            outcome="reported",
        )
    )
    return ledger


def test_family_and_sub_family_trial_counts_come_from_trial_ledger() -> None:
    matrix = build_trial_family_matrix(_ledger())

    assert matrix.family_id == "residual_price_volume_behavior"
    assert matrix.family_trial_count == 4
    assert matrix.sub_family_counts == {
        "residual_20d_momentum": 3,
        "abnormal_turnover_unwind": 1,
    }


def test_abandoned_trials_are_included_in_disclosure() -> None:
    report = build_multiple_testing_report(
        _ledger(),
        family_id="residual_price_volume_behavior",
        sub_family_id="residual_20d_momentum",
        selected_trial_id="trial-a",
        selected_metric="rank_ic_after_neutralization",
        selection_policy="pre_registered_top_rank_ic_with_all_trials_disclosed",
    )

    assert report.trial_count == 3
    assert "trial-c" in report.included_trial_ids
    assert report.outcome_counts["abandoned"] == 1


def test_dsr_and_pbo_are_marked_experimental_not_pass_gates() -> None:
    report = build_multiple_testing_report(
        _ledger(),
        family_id="residual_price_volume_behavior",
        sub_family_id="residual_20d_momentum",
        selected_trial_id="trial-a",
        selected_metric="rank_ic_after_neutralization",
        selection_policy="pre_registered_top_rank_ic_with_all_trials_disclosed",
    )

    assert report.dsr_experimental is True
    assert report.pbo_experimental is True
    assert "dsr_pbo_experimental_not_pass_gate" in report.warnings

