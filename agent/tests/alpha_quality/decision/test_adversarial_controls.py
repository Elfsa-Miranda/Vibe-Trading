from __future__ import annotations

from src.alpha_quality.decision.model import (
    AlphaQualityDecisionContext,
    HardFailureCode,
    QualityDecision,
)
from src.alpha_quality.decision.runner import QualityDecisionRunner
from src.alpha_quality.flags import ResolvedAGSFlags
from src.alpha_quality.model import AlphaQualityScorecard, ExecutionMetrics


def _scorecard(**kwargs: object) -> AlphaQualityScorecard:
    defaults = {
        "factor_id": "candidate",
        "formula": "rank(close)",
        "factor_definition_hash": "sha256:factor",
        "scope": "final_quality_decision",
        "horizons": [1],
        "execution": ExecutionMetrics(uses_execution_return=True, return_mean=0.01),
        "data_snapshot_ref": "snapshot:fixture",
        "trial_ledger_ref": "ledger:fixture",
    }
    defaults.update(kwargs)
    return AlphaQualityScorecard(**defaults)


def _runner() -> QualityDecisionRunner:
    return QualityDecisionRunner(
        flags=ResolvedAGSFlags.from_settings(
            {
                "VIBE_TRADING_AGS_ENABLED": "1",
                "VIBE_TRADING_ADMISSION_GATE": "1",
            }
        )
    )


def test_quality_decision_rejects_future_factor() -> None:
    result = _runner().run(
        _scorecard(formula="rank(future_return)"),
        AlphaQualityDecisionContext(),
    )

    assert result.decision == QualityDecision.REJECT
    assert HardFailureCode.LOOKAHEAD_DETECTED in result.hard_failures


def test_quality_decision_rejects_test_contamination() -> None:
    result = _runner().run(
        _scorecard(),
        AlphaQualityDecisionContext(
            trial_entries=[
                {
                    "candidate_id": "candidate",
                    "data_scope": "final_test",
                    "objective": "candidate_search",
                }
            ]
        ),
    )

    assert result.decision == QualityDecision.REJECT
    assert HardFailureCode.TEST_SET_CONTAMINATED in result.hard_failures


def test_quality_decision_caps_survivorship_bias() -> None:
    result = _runner().run(
        _scorecard(),
        AlphaQualityDecisionContext(survivorship_bias=True),
    )

    assert result.decision == QualityDecision.RESEARCH_ONLY
    assert HardFailureCode.PIT_CONTRACT_MISSING in result.hard_failures


def test_quality_decision_rejects_high_turnover_cost_blowup() -> None:
    result = _runner().run(
        _scorecard(
            execution=ExecutionMetrics(
                uses_execution_return=True,
                return_mean=-0.01,
                turnover_mean=80.0,
                cost_bps_mean=120.0,
            )
        ),
        AlphaQualityDecisionContext(),
    )

    assert result.decision == QualityDecision.REJECT
    assert HardFailureCode.COST_EXCEEDS_ALPHA in result.hard_failures


def test_scorecard_override_attempt_rejected() -> None:
    result = _runner().run(
        _scorecard(hard_failures=["LOOKAHEAD_DETECTED"]),
        AlphaQualityDecisionContext(),
    )

    assert result.decision == QualityDecision.REJECT
    assert HardFailureCode.LOOKAHEAD_DETECTED in result.hard_failures
