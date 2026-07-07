from __future__ import annotations

from datetime import datetime, timezone

from src.alpha_foundry.common.errors import HardFailureCode
from src.alpha_foundry.overfit.multiple_testing import build_multiple_testing_report
from src.alpha_foundry.overfit.trial_ledger import TrialLedger, TrialRecord


def _record(trial_id: str, outcome: str = "reported") -> TrialRecord:
    return TrialRecord(
        trial_id=trial_id,
        family_id="limit_liquidity_microstructure",
        sub_family_id="failed_limit_breakout_reversal",
        hypothesis_id="failed_limit_breakout_reversal",
        factor_id="failed_limit_breakout_reversal",
        factor_definition_hash="factor-hash",
        parameter_variant={"trial": trial_id},
        param_hash=f"param-{trial_id}",
        started_at=datetime(2026, 1, 5, tzinfo=timezone.utc),
        completed_at=datetime(2026, 1, 5, 1, tzinfo=timezone.utc),
        outcome=outcome,  # type: ignore[arg-type]
        report_ref=f"report-{trial_id}",
    )


def _ledger(count: int) -> TrialLedger:
    ledger = TrialLedger.create(
        ledger_id="ledger-limit",
        family_id="limit_liquidity_microstructure",
    )
    for idx in range(count):
        outcome = "selected" if idx == 0 else "rejected"
        ledger = ledger.append(_record(f"trial-{idx}", outcome=outcome))
    return ledger


def test_best_trial_without_trial_count_hard_fails() -> None:
    report = build_multiple_testing_report(
        None,
        family_id="limit_liquidity_microstructure",
        sub_family_id="failed_limit_breakout_reversal",
        selected_trial_id="trial-0",
        selected_metric="rank_ic_after_neutralization",
        strong_result_claim=True,
    )

    assert HardFailureCode.TRIAL_COUNT_MISSING in report.hard_failures
    assert HardFailureCode.BEST_TRIAL_ONLY in report.hard_failures
    assert report.trial_count is None


def test_high_trial_count_without_selection_policy_fails() -> None:
    report = build_multiple_testing_report(
        _ledger(3),
        family_id="limit_liquidity_microstructure",
        sub_family_id="failed_limit_breakout_reversal",
        selected_trial_id="trial-0",
        selected_metric="rank_ic_after_neutralization",
        strong_result_claim=True,
    )

    assert report.trial_count == 3
    assert HardFailureCode.MULTIPLE_TESTING_NOT_DISCLOSED in report.hard_failures


def test_selection_policy_satisfies_disclosure_gate() -> None:
    report = build_multiple_testing_report(
        _ledger(3),
        family_id="limit_liquidity_microstructure",
        sub_family_id="failed_limit_breakout_reversal",
        selected_trial_id="trial-0",
        selected_metric="rank_ic_after_neutralization",
        selection_policy="pre_registered_top_rank_ic_with_all_trials_disclosed",
        strong_result_claim=True,
    )

    assert report.trial_count == 3
    assert report.hard_failures == []

