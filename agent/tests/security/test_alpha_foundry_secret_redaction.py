from __future__ import annotations

from src.alpha_foundry.common.errors import HardFailureCode
from src.alpha_foundry.reports.builder import build_alpha_foundry_report, make_factor_candidate_card
from src.alpha_foundry.reports.render_markdown import render_alpha_foundry_report_markdown
from src.research_card.builder import build_alpha_foundry_research_card
from src.research_card.render_markdown import render_alpha_foundry_research_card_markdown
from src.reliability.quant.methodology_facts import AlphaFoundryMethodologyFacts
from src.reliability.quant.scorecard_policy import (
    AlphaFoundryClaim,
    AlphaFoundryClaimSet,
    evaluate_alpha_foundry_scorecard,
)


def test_alpha_foundry_markdown_escapes_xss_and_redacts_inline_secrets() -> None:
    malicious_note = (
        "<script>alert(1)</script> "
        "[click](javascript:alert(1)) "
        "token=ghp-fakefakefakefakefakefake "
        "sk-test-1234567890abcdef123456"
    )
    card = make_factor_candidate_card(
        factor_id="limit_queue_pressure_proxy",
        hypothesis_id="limit_queue_pressure_proxy",
        factor_definition_hash="hash-limit-queue",
        falsification_report_ref="falsification-limit-queue",
        hard_failures=[HardFailureCode.EOD_PROXY_OVERCLAIM],
        proxy_note=malicious_note,
        trial_count=8,
        uses_execution_return=True,
    )
    report = build_alpha_foundry_report(
        report_id="aaf-report",
        protocol_hash="protocol-hash",
        cards=[card],
        trial_ledger_ref="ledger-aaf",
    )
    claim_set = AlphaFoundryClaimSet(
        claim_set_id="claims-aaf",
        run_id="run-aaf",
        claims=[
            AlphaFoundryClaim(
                claim_id="claim-alpha",
                claim_type="alpha",
                claim_text="alpha claim",
                evidence_refs=[report.report_id],
            )
        ],
    )
    facts = AlphaFoundryMethodologyFacts(
        run_id="run-aaf",
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
    )
    scorecard = evaluate_alpha_foundry_scorecard(
        report=report,
        claim_set=claim_set,
        methodology_facts=facts,
    )
    research_card = build_alpha_foundry_research_card(report=report, scorecard=scorecard)

    rendered = "\n".join(
        [
            render_alpha_foundry_report_markdown(report),
            render_alpha_foundry_research_card_markdown(research_card),
        ]
    )

    assert "<script" not in rendered.lower()
    assert "javascript:" not in rendered.lower()
    assert "ghp-fakefakefakefakefakefake" not in rendered
    assert "sk-test-1234567890abcdef123456" not in rendered
    assert "[REDACTED]" in rendered
