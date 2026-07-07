from __future__ import annotations

import pytest

from src.alpha_foundry.common.errors import ConclusionLevel, HardFailureCode
from src.alpha_foundry.reports.builder import build_alpha_foundry_report, make_factor_candidate_card
from src.reliability.quant.methodology_facts import AlphaFoundryMethodologyFacts
from src.reliability.quant.scorecard_policy import (
    AlphaFoundryClaim,
    AlphaFoundryClaimSet,
    evaluate_alpha_foundry_scorecard,
)
from tests.alpha_foundry.fixtures.factory import make_alpha_foundry_factor_card_kwargs


CLAIM_TYPES = (
    "alpha",
    "tradable",
    "generalization",
    "factor_novelty",
    "portfolio_candidate",
    "paper_tracking_candidate",
    "risk_reduction",
    "execution_realism",
)


def _report():
    return build_alpha_foundry_report(
        report_id="aaf-report",
        protocol_hash="protocol-hash",
        cards=[make_factor_candidate_card(**make_alpha_foundry_factor_card_kwargs(proxy_note=None))],
        trial_ledger_ref="ledger-aaf",
    )


def _facts(**overrides: object) -> AlphaFoundryMethodologyFacts:
    payload = {
        "run_id": "run-aaf",
        "protocol_hash": "protocol-hash",
        "has_factor_formula": True,
        "uses_execution_return": True,
        "has_tradability_mask": True,
        "has_trial_ledger": True,
        "trial_count": 8,
        "has_multiple_testing_report": True,
        "has_risk_model": True,
        "risk_model_covariance_psd": True,
        "has_forward_plan": True,
        "forward_plan_frozen": True,
        "has_proxy_only_data": False,
        "has_benchmark": True,
    }
    payload.update(overrides)
    return AlphaFoundryMethodologyFacts(**payload)


def _claim_set(claim_type: str) -> AlphaFoundryClaimSet:
    return AlphaFoundryClaimSet(
        claim_set_id=f"claims-{claim_type}",
        run_id="run-aaf",
        claims=[
            AlphaFoundryClaim(
                claim_id=f"claim-{claim_type}",
                claim_type=claim_type,  # type: ignore[arg-type]
                claim_text=f"deterministic {claim_type} claim",
                evidence_refs=["aaf-report"],
            )
        ],
    )


@pytest.mark.parametrize("claim_type", CLAIM_TYPES)
def test_each_claim_type_has_positive_gate_fixture(claim_type: str) -> None:
    scorecard = evaluate_alpha_foundry_scorecard(
        report=_report(),
        claim_set=_claim_set(claim_type),
        methodology_facts=_facts(),
    )

    assert scorecard.hard_failures == []
    assert scorecard.conclusion_level == ConclusionLevel.research_candidate


@pytest.mark.parametrize(
    ("claim_type", "facts", "expected_failure"),
    [
        ("alpha", _facts(has_benchmark=False), HardFailureCode.BENCHMARK_MISSING),
        ("tradable", _facts(uses_execution_return=False), HardFailureCode.EXECUTION_RETURN_MISSING),
        ("generalization", _facts(has_trial_ledger=False, trial_count=None), HardFailureCode.TRIAL_COUNT_MISSING),
        ("factor_novelty", _facts(has_proxy_only_data=True), HardFailureCode.EOD_PROXY_OVERCLAIM),
        ("portfolio_candidate", _facts(has_risk_model=False), HardFailureCode.RISK_MODEL_MISSING),
        ("paper_tracking_candidate", _facts(forward_plan_frozen=False), HardFailureCode.FORWARD_PLAN_NOT_FROZEN),
        ("risk_reduction", _facts(risk_model_covariance_psd=False), HardFailureCode.RISK_MODEL_NOT_PSD),
        ("execution_realism", _facts(uses_execution_return=False), HardFailureCode.EXECUTION_RETURN_MISSING),
    ],
)
def test_each_claim_type_has_negative_gate_fixture(
    claim_type: str,
    facts: AlphaFoundryMethodologyFacts,
    expected_failure: HardFailureCode,
) -> None:
    scorecard = evaluate_alpha_foundry_scorecard(
        report=_report(),
        claim_set=_claim_set(claim_type),
        methodology_facts=facts,
    )

    assert expected_failure in scorecard.hard_failures
    assert scorecard.conclusion_level == ConclusionLevel.invalid


@pytest.mark.parametrize(
    ("claim_type", "facts", "expected_failure"),
    [
        ("alpha", _facts(has_factor_formula=False), HardFailureCode.FACTOR_FORMULA_AMBIGUOUS),
        ("alpha", _facts(has_proxy_only_data=True), HardFailureCode.EOD_PROXY_OVERCLAIM),
        ("alpha", _facts(has_trial_ledger=False, trial_count=None), HardFailureCode.TRIAL_COUNT_MISSING),
        ("alpha", _facts(has_benchmark=False), HardFailureCode.BENCHMARK_MISSING),
        ("portfolio_candidate", _facts(has_risk_model=False), HardFailureCode.RISK_MODEL_MISSING),
        ("portfolio_candidate", _facts(risk_model_covariance_psd=False), HardFailureCode.RISK_MODEL_NOT_PSD),
        ("tradable", _facts(uses_execution_return=False), HardFailureCode.EXECUTION_RETURN_MISSING),
        ("paper_tracking_candidate", _facts(forward_plan_frozen=False), HardFailureCode.FORWARD_PLAN_NOT_FROZEN),
    ],
)
def test_required_rules_emit_exact_failure_codes(
    claim_type: str,
    facts: AlphaFoundryMethodologyFacts,
    expected_failure: HardFailureCode,
) -> None:
    scorecard = evaluate_alpha_foundry_scorecard(
        report=_report(),
        claim_set=_claim_set(claim_type),
        methodology_facts=facts,
    )

    assert expected_failure in scorecard.hard_failures
    assert any(rule.error_code == expected_failure for rule in scorecard.triggered_rules)


def test_scorecard_override_attempt_is_hard_failure_and_cannot_upgrade() -> None:
    scorecard = evaluate_alpha_foundry_scorecard(
        report=_report(),
        claim_set=_claim_set("alpha"),
        methodology_facts=_facts(),
        requested_conclusion_level=ConclusionLevel.production_ready,
    )

    assert HardFailureCode.SCORECARD_OVERRIDE_ATTEMPT in scorecard.hard_failures
    assert scorecard.conclusion_level == ConclusionLevel.invalid
