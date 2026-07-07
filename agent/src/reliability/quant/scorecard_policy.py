"""Alpha Foundry scorecard policy gates over claims and methodology facts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.alpha_foundry.common.errors import ConclusionLevel, HardFailureCode
from src.alpha_foundry.reports.model import AlphaFoundryReport
from src.reliability.quant.methodology_facts import AlphaFoundryMethodologyFacts


AlphaFoundryClaimType = Literal[
    "alpha",
    "tradable",
    "generalization",
    "factor_novelty",
    "portfolio_candidate",
    "paper_tracking_candidate",
    "risk_reduction",
    "execution_realism",
]


class AlphaFoundryClaim(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "2.1.0"
    claim_id: str
    claim_type: AlphaFoundryClaimType
    claim_text: str
    evidence_refs: list[str] = Field(default_factory=list)


class AlphaFoundryClaimSet(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "2.1.0"
    claim_set_id: str
    run_id: str
    claims: list[AlphaFoundryClaim] = Field(default_factory=list)


class AlphaFoundryTriggeredRule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    rule_id: str
    error_code: HardFailureCode
    explanation: str
    evidence_refs: list[str] = Field(default_factory=list)


class AlphaFoundryScorecard(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "2.1.0"
    scorecard_id: str
    report_id: str
    claim_set_id: str
    conclusion_level: ConclusionLevel
    hard_failures: list[HardFailureCode] = Field(default_factory=list)
    triggered_rules: list[AlphaFoundryTriggeredRule] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @field_validator("hard_failures")
    @classmethod
    def _dedupe_hard_failures(cls, value: list[HardFailureCode]) -> list[HardFailureCode]:
        return _dedupe_failures(value)


STRONG_RESULT_CLAIMS = {
    "alpha",
    "generalization",
    "factor_novelty",
    "portfolio_candidate",
    "paper_tracking_candidate",
    "risk_reduction",
}


def evaluate_alpha_foundry_scorecard(
    *,
    report: AlphaFoundryReport,
    claim_set: AlphaFoundryClaimSet,
    methodology_facts: AlphaFoundryMethodologyFacts,
    requested_conclusion_level: ConclusionLevel | None = None,
) -> AlphaFoundryScorecard:
    rules: list[AlphaFoundryTriggeredRule] = []
    report_failures = list(report.hard_failures)
    for failure in report_failures:
        rules.append(
            AlphaFoundryTriggeredRule(
                rule_id="report_hard_failure",
                error_code=failure,
                explanation="AlphaFoundryReport already contains this hard failure.",
                evidence_refs=[report.report_id],
            )
        )

    claim_types = {claim.claim_type for claim in claim_set.claims}

    if requested_conclusion_level is not None:
        _append_rule(
            rules,
            "scorecard_override_attempt",
            HardFailureCode.SCORECARD_OVERRIDE_ATTEMPT,
            "External text or caller attempted to provide scorecard conclusion_level.",
            [report.report_id],
        )

    if claim_types and not methodology_facts.has_factor_formula:
        _append_rule(
            rules,
            "factor_formula_missing",
            HardFailureCode.FACTOR_FORMULA_AMBIGUOUS,
            "ClaimSet contains gated claims but factor formula evidence is missing.",
            [report.report_id],
        )

    if claim_types and methodology_facts.has_proxy_only_data:
        _append_rule(
            rules,
            "eod_proxy_overclaim",
            HardFailureCode.EOD_PROXY_OVERCLAIM,
            "Proxy-only EOD evidence cannot support unqualified Alpha Foundry claims.",
            [report.report_id],
        )

    if claim_types.intersection(STRONG_RESULT_CLAIMS) and (
        not methodology_facts.has_trial_ledger or methodology_facts.trial_count is None
    ):
        _append_rule(
            rules,
            "trial_count_missing",
            HardFailureCode.TRIAL_COUNT_MISSING,
            "Strong result claims require trial_count from TrialLedger.",
            [report.trial_ledger_ref or report.report_id],
        )

    if claim_types.intersection({"alpha", "portfolio_candidate"}) and not methodology_facts.has_benchmark:
        _append_rule(
            rules,
            "benchmark_missing",
            HardFailureCode.BENCHMARK_MISSING,
            "Alpha and portfolio claims require benchmark evidence.",
            [report.report_id],
        )

    if claim_types.intersection({"portfolio_candidate", "risk_reduction"}) and not methodology_facts.has_risk_model:
        _append_rule(
            rules,
            "risk_model_missing",
            HardFailureCode.RISK_MODEL_MISSING,
            "Portfolio and risk-reduction claims require a risk model snapshot.",
            [report.report_id],
        )

    if (
        claim_types.intersection({"portfolio_candidate", "risk_reduction"})
        and methodology_facts.has_risk_model
        and methodology_facts.risk_model_covariance_psd is False
    ):
        _append_rule(
            rules,
            "risk_model_not_psd",
            HardFailureCode.RISK_MODEL_NOT_PSD,
            "Risk model covariance must be PSD.",
            [report.report_id],
        )

    if claim_types.intersection({"tradable", "execution_realism"}) and not methodology_facts.uses_execution_return:
        _append_rule(
            rules,
            "execution_return_missing",
            HardFailureCode.EXECUTION_RETURN_MISSING,
            "Tradable validation must use execution_return, not only close_return.",
            [report.report_id],
        )

    if "paper_tracking_candidate" in claim_types and (
        not methodology_facts.has_forward_plan or not methodology_facts.forward_plan_frozen
    ):
        _append_rule(
            rules,
            "forward_plan_not_frozen",
            HardFailureCode.FORWARD_PLAN_NOT_FROZEN,
            "Paper tracking candidate claims require a frozen forward tracking plan.",
            report.forward_plan_refs or [report.report_id],
        )

    failures = _dedupe_failures([rule.error_code for rule in rules])
    conclusion = ConclusionLevel.invalid if failures else _cap_report_conclusion(report.conclusion_level)
    warnings = list(report.warnings)
    if not failures and not methodology_facts.has_tradability_mask:
        conclusion = _min_conclusion(conclusion, ConclusionLevel.exploratory)
        warnings.append("tradability_mask_missing_caps_exploratory")
    if not failures and conclusion == ConclusionLevel.production_ready:
        conclusion = ConclusionLevel.research_candidate
        warnings.append("production_ready_unreachable_in_v2_1")

    return AlphaFoundryScorecard(
        scorecard_id=f"scorecard-{report.report_id}",
        report_id=report.report_id,
        claim_set_id=claim_set.claim_set_id,
        conclusion_level=conclusion,
        hard_failures=failures,
        triggered_rules=rules,
        warnings=_dedupe_strings(warnings),
    )


def _append_rule(
    rules: list[AlphaFoundryTriggeredRule],
    rule_id: str,
    error_code: HardFailureCode,
    explanation: str,
    evidence_refs: list[str],
) -> None:
    rules.append(
        AlphaFoundryTriggeredRule(
            rule_id=rule_id,
            error_code=error_code,
            explanation=explanation,
            evidence_refs=evidence_refs,
        )
    )


def _cap_report_conclusion(level: ConclusionLevel) -> ConclusionLevel:
    if level == ConclusionLevel.production_ready:
        return ConclusionLevel.research_candidate
    return level


_CONCLUSION_RANK = {
    ConclusionLevel.invalid: 0,
    ConclusionLevel.exploratory: 1,
    ConclusionLevel.research_candidate: 2,
    ConclusionLevel.paper_tracking_candidate: 3,
    ConclusionLevel.production_ready: 4,
}


def _min_conclusion(left: ConclusionLevel, right: ConclusionLevel) -> ConclusionLevel:
    return min(left, right, key=lambda item: _CONCLUSION_RANK[item])


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
