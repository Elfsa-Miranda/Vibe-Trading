"""Methodology facts for Alpha Foundry scorecard predicates."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from src.alpha_foundry.overfit.trial_ledger import TrialLedger
from src.alpha_foundry.reports.model import AlphaFoundryReport


class AlphaFoundryMethodologyFacts(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "2.1.0"
    run_id: str
    protocol_hash: str | None = None
    has_factor_formula: bool = False
    uses_execution_return: bool = False
    has_tradability_mask: bool = False
    has_trial_ledger: bool = False
    trial_count: int | None = None
    has_multiple_testing_report: bool = False
    has_risk_model: bool = False
    risk_model_covariance_psd: bool | None = None
    has_forward_plan: bool = False
    forward_plan_frozen: bool = False
    has_proxy_only_data: bool = False
    has_benchmark: bool = False
    generated_from_artifacts: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def derive_alpha_foundry_methodology_facts(
    report: AlphaFoundryReport,
    *,
    run_id: str = "run-aaf",
    trial_ledger: TrialLedger | None = None,
    trial_count: int | None = None,
    has_trial_ledger: bool | None = None,
    has_tradability_mask: bool = False,
    uses_execution_return: bool = False,
    has_multiple_testing_report: bool = False,
    has_risk_model: bool = False,
    risk_model_covariance_psd: bool | None = None,
    has_forward_plan: bool = False,
    forward_plan_frozen: bool = False,
    has_benchmark: bool = False,
) -> AlphaFoundryMethodologyFacts:
    ledger_count = trial_ledger.trial_count() if trial_ledger is not None else trial_count
    ledger_present = (trial_ledger is not None) if has_trial_ledger is None else has_trial_ledger
    has_formula = bool(report.factor_candidate_cards) and all(
        bool(card.factor_definition_hash) for card in report.factor_candidate_cards
    )
    return AlphaFoundryMethodologyFacts(
        run_id=run_id,
        protocol_hash=report.protocol_hash,
        has_factor_formula=has_formula,
        uses_execution_return=uses_execution_return,
        has_tradability_mask=has_tradability_mask,
        has_trial_ledger=ledger_present,
        trial_count=ledger_count,
        has_multiple_testing_report=has_multiple_testing_report,
        has_risk_model=has_risk_model,
        risk_model_covariance_psd=risk_model_covariance_psd,
        has_forward_plan=has_forward_plan,
        forward_plan_frozen=forward_plan_frozen,
        has_proxy_only_data=any(bool(card.proxy_note) for card in report.factor_candidate_cards),
        has_benchmark=has_benchmark,
        generated_from_artifacts=[
            card.falsification_report_ref
            for card in report.factor_candidate_cards
            if card.falsification_report_ref
        ],
    )
