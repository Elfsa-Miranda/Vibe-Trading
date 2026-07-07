"""Builders for Alpha Foundry report artifacts."""

from __future__ import annotations

from src.alpha_foundry.common.errors import ConclusionLevel, HardFailureCode
from src.alpha_foundry.reports.model import AlphaFoundryReport, FactorCandidateCard


_CONCLUSION_RANK = {
    ConclusionLevel.invalid: 0,
    ConclusionLevel.exploratory: 1,
    ConclusionLevel.research_candidate: 2,
    ConclusionLevel.paper_tracking_candidate: 3,
    ConclusionLevel.production_ready: 4,
}


def make_factor_candidate_card(
    *,
    factor_id: str,
    hypothesis_id: str,
    factor_definition_hash: str,
    falsification_report_ref: str,
    card_id: str | None = None,
    conclusion_level: ConclusionLevel = ConclusionLevel.exploratory,
    key_metrics: dict[str, float | None] | None = None,
    hard_failures: list[HardFailureCode] | None = None,
    warnings: list[str] | None = None,
    next_action: str | None = None,
    trial_count: int | None = None,
    proxy_note: str | None = None,
    uses_execution_return: bool = False,
    has_close_return_diagnostics: bool = True,
    evidence_refs: list[str] | None = None,
) -> FactorCandidateCard:
    failures = _dedupe_failures(hard_failures or [])
    card_conclusion = ConclusionLevel.invalid if failures else _cap_production_ready(conclusion_level)
    resolved_next_action = next_action or ("reject" if failures else "portfolio_test")
    return FactorCandidateCard(
        card_id=card_id or f"factor-card-{factor_id}",
        factor_id=factor_id,
        hypothesis_id=hypothesis_id,
        factor_definition_hash=factor_definition_hash,
        falsification_report_ref=falsification_report_ref,
        conclusion_level=card_conclusion,
        key_metrics=key_metrics or {},
        hard_failures=failures,
        warnings=_dedupe_strings(warnings or []),
        next_action=resolved_next_action,  # type: ignore[arg-type]
        trial_count=trial_count,
        proxy_note=proxy_note,
        uses_execution_return=uses_execution_return,
        has_close_return_diagnostics=has_close_return_diagnostics,
        evidence_refs=_dedupe_strings(evidence_refs or []),
    )


def build_alpha_foundry_report(
    *,
    report_id: str,
    protocol_hash: str,
    cards: list[FactorCandidateCard],
    portfolio_report_refs: list[str] | None = None,
    forward_plan_refs: list[str] | None = None,
    trial_ledger_ref: str | None = None,
    requested_conclusion_level: ConclusionLevel | None = None,
    warnings: list[str] | None = None,
    research_card_ref: str | None = None,
) -> AlphaFoundryReport:
    hard_failures: list[HardFailureCode] = []
    report_warnings = list(warnings or [])
    for card in cards:
        hard_failures.extend(card.hard_failures)
        report_warnings.extend(card.warnings)

    failures = _dedupe_failures(hard_failures)
    if failures:
        conclusion = ConclusionLevel.invalid
    else:
        conclusion = _resolve_report_conclusion(cards, requested_conclusion_level)
        if requested_conclusion_level == ConclusionLevel.production_ready:
            report_warnings.append("production_ready_unreachable_in_v2_1")

    return AlphaFoundryReport(
        report_id=report_id,
        protocol_hash=protocol_hash,
        hypothesis_refs=_dedupe_strings([card.hypothesis_id for card in cards]),
        factor_candidate_cards=cards,
        portfolio_report_refs=_dedupe_strings(portfolio_report_refs or []),
        forward_plan_refs=_dedupe_strings(forward_plan_refs or []),
        trial_ledger_ref=trial_ledger_ref,
        conclusion_level=conclusion,
        hard_failures=failures,
        warnings=_dedupe_strings(report_warnings),
        research_card_ref=research_card_ref,
    )


def _resolve_report_conclusion(
    cards: list[FactorCandidateCard],
    requested_conclusion_level: ConclusionLevel | None,
) -> ConclusionLevel:
    if not cards:
        return ConclusionLevel.exploratory
    card_level = min((card.conclusion_level for card in cards), key=lambda item: _CONCLUSION_RANK[item])
    if requested_conclusion_level is None:
        return _cap_production_ready(card_level)
    requested = _cap_production_ready(requested_conclusion_level)
    return min(card_level, requested, key=lambda item: _CONCLUSION_RANK[item])


def _cap_production_ready(level: ConclusionLevel) -> ConclusionLevel:
    if level == ConclusionLevel.production_ready:
        return ConclusionLevel.research_candidate
    return level


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
