"""Research Card integration for Alpha Foundry reports."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.alpha_foundry.common.errors import ConclusionLevel, HardFailureCode
from src.alpha_foundry.reports.model import AlphaFoundryReport
from src.reliability.quant.scorecard_policy import AlphaFoundryScorecard


class AlphaFoundryResearchCard(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "2.1.0"
    card_id: str
    report_ref: str
    scorecard_ref: str
    conclusion_level: ConclusionLevel
    hard_failures: list[HardFailureCode] = Field(default_factory=list)
    trial_count: int | None = None
    factor_definition_hashes: list[str] = Field(default_factory=list)
    proxy_notes: list[str] = Field(default_factory=list)
    uses_execution_return: bool = False
    has_close_return_diagnostics: bool = False
    warnings: list[str] = Field(default_factory=list)

    @field_validator("hard_failures")
    @classmethod
    def _dedupe_hard_failures(cls, value: list[HardFailureCode]) -> list[HardFailureCode]:
        return _dedupe_failures(value)

    @field_validator("factor_definition_hashes", "proxy_notes", "warnings")
    @classmethod
    def _dedupe_strings(cls, value: list[str]) -> list[str]:
        return _dedupe_strings(value)


def build_alpha_foundry_research_card(
    *,
    report: AlphaFoundryReport,
    scorecard: AlphaFoundryScorecard,
    assistant_summary: str | None = None,
) -> AlphaFoundryResearchCard:
    warnings = list(scorecard.warnings)
    if assistant_summary:
        warnings.append("assistant_summary_excluded_from_gates")

    return AlphaFoundryResearchCard(
        card_id=f"research-card-{report.report_id}",
        report_ref=report.report_id,
        scorecard_ref=scorecard.scorecard_id,
        conclusion_level=scorecard.conclusion_level,
        hard_failures=scorecard.hard_failures,
        trial_count=_resolve_trial_count(report),
        factor_definition_hashes=[
            card.factor_definition_hash
            for card in report.factor_candidate_cards
            if card.factor_definition_hash
        ],
        proxy_notes=[card.proxy_note for card in report.factor_candidate_cards if card.proxy_note],
        uses_execution_return=any(card.uses_execution_return for card in report.factor_candidate_cards),
        has_close_return_diagnostics=any(
            card.has_close_return_diagnostics for card in report.factor_candidate_cards
        ),
        warnings=warnings,
    )


def build_alpha_foundry_card_consistency_fixture(
    *,
    card: AlphaFoundryResearchCard,
    scorecard: AlphaFoundryScorecard,
) -> dict[str, dict[str, object]]:
    failures = [failure.value for failure in scorecard.hard_failures]
    card_failures = [failure.value for failure in card.hard_failures]
    return {
        "research_card": {
            "hard_failures": card_failures,
            "conclusion_level": card.conclusion_level.value,
        },
        "scorecard": {
            "hard_failures": failures,
            "conclusion_level": scorecard.conclusion_level.value,
        },
        "api_fixture": {
            "hard_failures": failures,
            "conclusion_level": scorecard.conclusion_level.value,
        },
        "ui_fixture": {
            "hard_failures": failures,
            "conclusion_level": scorecard.conclusion_level.value,
        },
    }


def _resolve_trial_count(report: AlphaFoundryReport) -> int | None:
    counts = [card.trial_count for card in report.factor_candidate_cards if card.trial_count is not None]
    if not counts:
        return None
    return max(counts)


def _dedupe_failures(values: list[HardFailureCode]) -> list[HardFailureCode]:
    output: list[HardFailureCode] = []
    for value in values:
        if value not in output:
            output.append(value)
    return output


def _dedupe_strings(values: list[str]) -> list[str]:
    output: list[str] = []
    for value in values:
        if value not in output:
            output.append(value)
    return output
