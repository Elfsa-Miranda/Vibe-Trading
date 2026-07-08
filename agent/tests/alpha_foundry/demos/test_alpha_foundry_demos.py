from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


DEMO_ROOT = Path("agent/examples/alpha_foundry_demos")
DEMOS = (
    "naive_limit_momentum_trap",
    "failed_limit_breakout_candidate",
    "public_alpha_crowding_trap",
    "orthogonal_portfolio_increment",
    "forward_decay_kill",
)


def test_all_demo_dry_runs_match_snapshots() -> None:
    for demo in DEMOS:
        result = subprocess.run(
            [sys.executable, str(DEMO_ROOT / demo / "runner.py"), "--dry-run"],
            check=True,
            capture_output=True,
            text=True,
        )
        assert "snapshot_match" in result.stdout


def test_demo_snapshots_contain_required_evidence_fields() -> None:
    for demo in DEMOS:
        snapshot = _snapshot(demo)
        assert snapshot["schema_version"] == "2.1.0"
        assert snapshot["demo_name"] == demo
        assert snapshot["report_ref"]
        assert snapshot["research_card_ref"]
        assert snapshot["trial_ledger"]["source"] == "TrialLedger"
        assert isinstance(snapshot["trial_ledger"]["trial_count"], int)
        assert snapshot["factor_definition_hashes"]
        assert "error_codes" in snapshot


def test_failed_limit_breakout_candidate_meets_research_candidate_thresholds() -> None:
    snapshot = _snapshot("failed_limit_breakout_candidate")

    assert snapshot["conclusion_level"] == "research_candidate"
    assert snapshot["metrics"]["rank_ic_after_neutralization"] > 0.02
    assert snapshot["metrics"]["t_stat_after_neutralization"] > 1.5
    assert snapshot["metrics"]["placebo_max_rank_ic"] < snapshot["metrics"]["rank_ic_after_neutralization"]
    assert snapshot["metrics"]["regime_negative_fraction"] < 0.40
    assert snapshot["falsified"] is False
    assert snapshot["trial_ledger"]["trial_count"] >= 1


def test_forward_decay_kill_demo_records_append_only_mutation_failure() -> None:
    snapshot = _snapshot("forward_decay_kill")

    assert snapshot["forward_status"] == "killed"
    assert snapshot["mutation_error"] == "duplicate observation_id rejected"


def _snapshot(demo: str) -> dict:
    return json.loads((DEMO_ROOT / demo / "expected_output.json").read_text(encoding="utf-8"))
