from __future__ import annotations

from src.alpha_foundry.common.errors import ConclusionLevel, HardFailureCode
from src.alpha_foundry.reports.builder import build_alpha_foundry_report, make_factor_candidate_card
from src.reliability.quant.methodology_facts import AlphaFoundryMethodologyFacts
from src.reliability.quant.scorecard_policy import (
    AlphaFoundryClaim,
    AlphaFoundryClaimSet,
    evaluate_alpha_foundry_scorecard,
)


def _claim_set() -> AlphaFoundryClaimSet:
    return AlphaFoundryClaimSet(
        claim_set_id="claims-aaf",
        run_id="run-aaf",
        claims=[
            AlphaFoundryClaim(
                claim_id="claim-portfolio",
                claim_type="portfolio_candidate",
                claim_text="portfolio candidate claim",
                evidence_refs=["aaf-report"],
            )
        ],
    )


def _facts(**overrides: object) -> AlphaFoundryMethodologyFacts:
    payload = {
        "run_id": "run-aaf",
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


def test_scorecard_rejects_override_and_non_psd_portfolio_claim() -> None:
    report = build_alpha_foundry_report(
        report_id="aaf-report",
        protocol_hash="protocol-hash",
        cards=[
            make_factor_candidate_card(
                factor_id="residual_20d_momentum",
                hypothesis_id="residual_20d_momentum",
                factor_definition_hash="hash-residual",
                falsification_report_ref="falsification-residual",
                trial_count=8,
                uses_execution_return=True,
            )
        ],
        trial_ledger_ref="ledger-aaf",
    )

    scorecard = evaluate_alpha_foundry_scorecard(
        report=report,
        claim_set=_claim_set(),
        methodology_facts=_facts(risk_model_covariance_psd=False),
        requested_conclusion_level=ConclusionLevel.production_ready,
    )

    assert scorecard.conclusion_level == ConclusionLevel.invalid
    assert set(scorecard.hard_failures) == {
        HardFailureCode.RISK_MODEL_NOT_PSD,
        HardFailureCode.SCORECARD_OVERRIDE_ATTEMPT,
    }
    assert {rule.error_code for rule in scorecard.triggered_rules} == set(scorecard.hard_failures)
