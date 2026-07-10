from __future__ import annotations

from dataclasses import fields

import pytest

from src.alpha_quality.decision.model import AlphaQualityDecisionContext, QualityDecision
from src.alpha_quality.decision.runner import QualityDecisionRunner
from src.alpha_quality.flags import ResolvedAGSFlags
from src.alpha_quality.model import AlphaQualityScorecard, ExecutionMetrics


def _scorecard() -> AlphaQualityScorecard:
    return AlphaQualityScorecard(
        factor_id="candidate",
        formula="rank(close)",
        factor_definition_hash="sha256:factor",
        scope="final_quality_decision",
        horizons=[1],
        execution=ExecutionMetrics(uses_execution_return=True, return_mean=0.01),
        data_snapshot_ref="sha256:snapshot",
        trial_ledger_ref="ledger:fixture",
    )


def _legacy_flags() -> ResolvedAGSFlags:
    return ResolvedAGSFlags.from_settings(
        {
            "VIBE_TRADING_AGS_ENABLED": "1",
            "VIBE_TRADING_ADMISSION_GATE": "1",
        }
    )


def test_caller_cannot_supply_decision_failures_caps_or_total_score() -> None:
    public_fields = {item.name for item in fields(AlphaQualityDecisionContext)}

    assert public_fields.isdisjoint(
        {
            "decision",
            "caller_claimed_decision",
            "total_quality_score",
            "hard_failures",
            "warnings",
            "caps",
            "cap_reasons",
        }
    )
    with pytest.raises(TypeError):
        AlphaQualityDecisionContext(total_quality_score=1.0)  # type: ignore[call-arg]


def test_v1_compatibility_runner_rebuilds_score_internally() -> None:
    result = QualityDecisionRunner(flags=_legacy_flags()).run(
        _scorecard(), AlphaQualityDecisionContext()
    )

    assert result.decision == QualityDecision.RESEARCH_ONLY
    assert result.total_quality_score == 0.15


def test_v1_compatibility_runner_is_unavailable_without_legacy_capability() -> None:
    with pytest.raises(RuntimeError, match="legacy admission gate is disabled"):
        QualityDecisionRunner(flags=ResolvedAGSFlags.from_settings({})).run(
            _scorecard(), AlphaQualityDecisionContext()
        )
