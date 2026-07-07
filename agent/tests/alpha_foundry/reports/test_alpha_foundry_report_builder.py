from __future__ import annotations

from src.alpha_foundry.common.errors import ConclusionLevel, HardFailureCode
from src.alpha_foundry.reports.builder import build_alpha_foundry_report, make_factor_candidate_card
from src.alpha_foundry.reports.render_markdown import render_alpha_foundry_report_markdown
from tests.alpha_foundry.fixtures.factory import make_alpha_foundry_factor_card_kwargs


def test_alpha_foundry_report_schema_aggregates_exact_error_codes() -> None:
    card = make_factor_candidate_card(
        **make_alpha_foundry_factor_card_kwargs(
            hard_failures=[HardFailureCode.EOD_PROXY_OVERCLAIM],
            proxy_note="EOD proxy only; no Level-2 queue alpha claim.",
        )
    )

    report = build_alpha_foundry_report(
        report_id="aaf-report",
        protocol_hash="protocol-hash",
        cards=[card],
        trial_ledger_ref="ledger-1",
    )

    assert report.schema_version == "2.1.0"
    assert report.conclusion_level == ConclusionLevel.invalid
    assert report.hard_failures == [HardFailureCode.EOD_PROXY_OVERCLAIM]
    assert report.factor_candidate_cards[0].proxy_note.startswith("EOD proxy")


def test_alpha_foundry_report_caps_production_ready_to_research_candidate() -> None:
    card = make_factor_candidate_card(
        **make_alpha_foundry_factor_card_kwargs(
            factor_id="residual_20d_momentum",
            proxy_note=None,
            hard_failures=[],
        )
    )

    report = build_alpha_foundry_report(
        report_id="aaf-report",
        protocol_hash="protocol-hash",
        cards=[card],
        requested_conclusion_level=ConclusionLevel.production_ready,
    )

    assert report.conclusion_level == ConclusionLevel.research_candidate
    assert report.hard_failures == []
    assert "production_ready_unreachable_in_v2_1" in report.warnings


def test_alpha_foundry_report_markdown_keeps_return_track_distinction() -> None:
    card = make_factor_candidate_card(
        **make_alpha_foundry_factor_card_kwargs(
            hard_failures=[],
            proxy_note="EOD proxy only; no Level-2 queue alpha claim.",
            uses_execution_return=True,
        )
    )

    report = build_alpha_foundry_report(
        report_id="aaf-report",
        protocol_hash="protocol-hash",
        cards=[card],
        trial_ledger_ref="ledger-1",
    )

    markdown = render_alpha_foundry_report_markdown(report)

    assert "execution_return used for tradable validation" in markdown
    assert "close_return shown only as diagnostics" in markdown
    assert "EOD proxy only; no Level-2 queue alpha claim." in markdown
