from __future__ import annotations

from src.alpha_foundry.common.errors import HardFailureCode
from src.alpha_foundry.reports.builder import build_alpha_foundry_report, make_factor_candidate_card
from src.reliability.quant.methodology_facts import AlphaFoundryMethodologyFacts
from src.reliability.quant.scorecard_policy import (
    AlphaFoundryClaim,
    AlphaFoundryClaimSet,
    evaluate_alpha_foundry_scorecard,
)
from src.research_card.builder import build_alpha_foundry_research_card
from src.research_card.render_markdown import render_alpha_foundry_research_card_markdown
from tests.alpha_foundry.fixtures.factory import make_alpha_foundry_factor_card_kwargs


def test_alpha_foundry_research_card_markdown_renders_exact_codes_and_proxy_notes() -> None:
    report = build_alpha_foundry_report(
        report_id="aaf-report",
        protocol_hash="protocol-hash",
        cards=[
            make_factor_candidate_card(
                **make_alpha_foundry_factor_card_kwargs(
                    hard_failures=[HardFailureCode.EOD_PROXY_OVERCLAIM],
                    trial_count=8,
                    proxy_note="EOD proxy only; no Level-2 queue alpha claim.",
                )
            )
        ],
        trial_ledger_ref="ledger-aaf",
    )
    scorecard = evaluate_alpha_foundry_scorecard(
        report=report,
        claim_set=AlphaFoundryClaimSet(
            claim_set_id="claims-alpha",
            run_id="run-aaf",
            claims=[
                AlphaFoundryClaim(
                    claim_id="claim-alpha",
                    claim_type="alpha",
                    claim_text="EOD proxy demonstrates alpha",
                    evidence_refs=["aaf-report"],
                )
            ],
        ),
        methodology_facts=AlphaFoundryMethodologyFacts(
            run_id="run-aaf",
            protocol_hash="protocol-hash",
            has_factor_formula=True,
            uses_execution_return=True,
            has_tradability_mask=True,
            has_trial_ledger=True,
            trial_count=8,
            has_multiple_testing_report=True,
            has_risk_model=True,
            risk_model_covariance_psd=True,
            has_forward_plan=True,
            forward_plan_frozen=True,
            has_proxy_only_data=True,
            has_benchmark=True,
        ),
    )
    card = build_alpha_foundry_research_card(report=report, scorecard=scorecard)

    markdown = render_alpha_foundry_research_card_markdown(card)

    assert "EOD_PROXY_OVERCLAIM" in markdown
    assert "Trial count: 8" in markdown
    assert "hash-limit_queue_pressure_proxy" in markdown
    assert "EOD proxy only; no Level-2 queue alpha claim." in markdown
    assert "execution_return used for tradable validation" in markdown
    assert "close_return shown only as diagnostics" in markdown
