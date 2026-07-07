"""Deterministic factor falsification engine."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from src.alpha_foundry.common.errors import ConclusionLevel, HardFailureCode
from src.alpha_foundry.common.hashing import canonical_hash
from src.alpha_foundry.diagnostics.controls import placebo_max_rank_ic
from src.alpha_foundry.diagnostics.decay import estimate_decay_half_life_days
from src.alpha_foundry.diagnostics.ic import ICSummary, compute_ic_summary
from src.alpha_foundry.diagnostics.neutralization import neutralize_factor_frame
from src.alpha_foundry.diagnostics.regime import negative_regime_fraction
from src.alpha_foundry.diagnostics.turnover import compute_factor_turnover
from src.alpha_foundry.overfit.trial_ledger import TrialLedger, TrialRecord


NEUTRALIZATION_COLLAPSE_DELTA = 0.02
WEAK_NEUTRALIZED_IC_ABS = 0.015
PLACEBO_COMPARABLE_DELTA = 0.005
RESEARCH_CANDIDATE_RANK_IC = 0.02
RESEARCH_CANDIDATE_T_STAT = 1.5
ICIR_WEAK_THRESHOLD = 0.5
REGIME_NEGATIVE_FRACTION_THRESHOLD = 0.40


class FactorFalsificationReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "2.1.0"
    report_id: str
    factor_id: str
    hypothesis_id: str
    trial_id: str
    protocol_hash: str
    ic_raw: float | None = None
    rank_ic_raw: float | None = None
    ic_industry_neutral: float | None = None
    rank_ic_industry_neutral: float | None = None
    ic_size_neutral: float | None = None
    rank_ic_size_neutral: float | None = None
    ic_after_neutralization: float | None = None
    rank_ic_after_neutralization: float | None = None
    icir_after_neutralization: float | None = None
    t_stat_after_neutralization: float | None = None
    placebo_max_rank_ic: float | None = None
    regime_negative_fraction: float | None = None
    decay_half_life_days: float | None = None
    factor_turnover: float | None = None
    cost_breakeven_bps: float | None = None
    execution_return_used: bool = False
    falsified: bool
    conclusion_cap: ConclusionLevel
    hard_failures: list[HardFailureCode] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


def run_factor_falsification(
    factor_frame: pd.DataFrame,
    forward_returns: pd.DataFrame,
    *,
    factor_id: str,
    hypothesis_id: str,
    track: str,
    factor_definition_hash: str,
    protocol_hash: str,
    ledger: TrialLedger,
    exposures: pd.DataFrame | None = None,
    return_column: str = "close_return",
    placebo_rank_ics: list[float] | None = None,
    regime_ic: dict[str, float] | None = None,
    horizon_rank_ics: dict[int, float] | None = None,
    parameter_variant: dict[str, Any] | None = None,
    diagnostics_params: dict[str, Any] | None = None,
) -> tuple[FactorFalsificationReport, TrialLedger]:
    started_at = _utc_now()
    raw = compute_ic_summary(factor_frame, forward_returns, return_column=return_column)

    warnings: list[str] = []
    if exposures is not None:
        neutralized = neutralize_factor_frame(factor_frame, exposures)
        neutralized_frame = neutralized.frame
        warnings.extend(neutralized.warnings)
    else:
        neutralized_frame = factor_frame
        warnings.append("neutralization_exposures_missing")

    after = compute_ic_summary(neutralized_frame, forward_returns, return_column=return_column)
    rank_ic_values = _clean_metric_values(after.rank_ic_by_date.values())
    icir = _icir(rank_ic_values)
    t_stat = _t_stat(rank_ic_values)
    placebo_max = placebo_max_rank_ic(placebo_rank_ics)
    regime_negative = negative_regime_fraction(regime_ic)
    decay_half_life = estimate_decay_half_life_days(horizon_rank_ics)
    turnover = compute_factor_turnover(factor_frame)

    hard_failures = _evaluate_hard_failures(
        track=track,
        return_column=return_column,
        raw=raw,
        after=after,
        placebo_max=placebo_max,
        regime_negative_fraction_value=regime_negative,
    )
    warnings.extend(_evaluate_warnings(after=after, icir=icir, decay_half_life_days=decay_half_life))
    hard_failures = _dedupe_failures(hard_failures)
    warnings = sorted(set(warnings))

    conclusion_cap = _conclusion_cap(
        hard_failures=hard_failures,
        rank_ic_after=after.rank_ic_raw,
        t_stat_after=t_stat,
    )
    falsified = bool(hard_failures)
    trial_id = f"trial-{uuid4()}"
    report_id = f"falsification-{uuid4()}"

    report = FactorFalsificationReport(
        report_id=report_id,
        factor_id=factor_id,
        hypothesis_id=hypothesis_id,
        trial_id=trial_id,
        protocol_hash=protocol_hash,
        ic_raw=raw.ic_raw,
        rank_ic_raw=raw.rank_ic_raw,
        ic_industry_neutral=after.ic_raw,
        rank_ic_industry_neutral=after.rank_ic_raw,
        ic_size_neutral=after.ic_raw,
        rank_ic_size_neutral=after.rank_ic_raw,
        ic_after_neutralization=after.ic_raw,
        rank_ic_after_neutralization=after.rank_ic_raw,
        icir_after_neutralization=icir,
        t_stat_after_neutralization=t_stat,
        placebo_max_rank_ic=placebo_max,
        regime_negative_fraction=regime_negative,
        decay_half_life_days=decay_half_life,
        factor_turnover=turnover,
        cost_breakeven_bps=None,
        execution_return_used=return_column == "execution_return",
        falsified=falsified,
        conclusion_cap=conclusion_cap,
        hard_failures=hard_failures,
        warnings=warnings,
        evidence_refs=[],
    )

    completed_at = _utc_now()
    parameter_variant = parameter_variant or {}
    diagnostics_params = diagnostics_params or {"return_column": return_column}
    record = TrialRecord(
        trial_id=trial_id,
        family_id=track,
        sub_family_id=hypothesis_id,
        hypothesis_id=hypothesis_id,
        factor_id=factor_id,
        factor_definition_hash=factor_definition_hash,
        parameter_variant=parameter_variant,
        param_hash=canonical_hash(
            {
                "factor_id": factor_id,
                "factor_definition_hash": factor_definition_hash,
                "parameter_variant": parameter_variant,
                "diagnostics_params": diagnostics_params,
            }
        ),
        started_at=started_at,
        completed_at=completed_at,
        outcome=_trial_outcome(report),
        rejection_reason=",".join(failure.value for failure in hard_failures) if hard_failures else None,
        report_ref=report.report_id,
    )
    return report, ledger.append(record)


def _evaluate_hard_failures(
    *,
    track: str,
    return_column: str,
    raw: ICSummary,
    after: ICSummary,
    placebo_max: float | None,
    regime_negative_fraction_value: float | None,
) -> list[HardFailureCode]:
    failures: list[HardFailureCode] = []
    raw_rank = raw.rank_ic_raw or 0.0
    after_rank = after.rank_ic_raw or 0.0

    if track == "limit_liquidity_microstructure" and return_column != "execution_return":
        failures.append(HardFailureCode.EXECUTION_RETURN_MISSING)

    if (
        abs(raw_rank - after_rank) > NEUTRALIZATION_COLLAPSE_DELTA
        and abs(after_rank) < WEAK_NEUTRALIZED_IC_ABS
    ):
        failures.append(HardFailureCode.NEUTRALIZED_IC_COLLAPSE)

    if placebo_max is not None:
        if abs(after_rank - placebo_max) < PLACEBO_COMPARABLE_DELTA or abs(placebo_max) > abs(after_rank):
            failures.append(HardFailureCode.PLACEBO_COMPARABLE)

    if regime_negative_fraction_value is not None and regime_negative_fraction_value > REGIME_NEGATIVE_FRACTION_THRESHOLD:
        failures.append(HardFailureCode.REGIME_FAILURE)

    return failures


def _evaluate_warnings(
    *,
    after: ICSummary,
    icir: float | None,
    decay_half_life_days: float | None,
) -> list[str]:
    warnings: list[str] = []
    after_rank = after.rank_ic_raw or 0.0
    if abs(after_rank) < WEAK_NEUTRALIZED_IC_ABS:
        warnings.append("weak_neutralized_ic_abs_lt_0.015")
    if icir is not None and icir < ICIR_WEAK_THRESHOLD:
        warnings.append("icir_after_neutralization_lt_0.5")
    if decay_half_life_days is not None and decay_half_life_days < 2:
        warnings.append("decay_half_life_lt_2_days")
    return warnings


def _conclusion_cap(
    *,
    hard_failures: list[HardFailureCode],
    rank_ic_after: float | None,
    t_stat_after: float | None,
) -> ConclusionLevel:
    if HardFailureCode.PLACEBO_COMPARABLE in hard_failures or HardFailureCode.EXECUTION_RETURN_MISSING in hard_failures:
        return ConclusionLevel.invalid
    if hard_failures:
        return ConclusionLevel.exploratory
    if (
        rank_ic_after is not None
        and t_stat_after is not None
        and rank_ic_after > RESEARCH_CANDIDATE_RANK_IC
        and t_stat_after > RESEARCH_CANDIDATE_T_STAT
    ):
        return ConclusionLevel.research_candidate
    return ConclusionLevel.exploratory


def _trial_outcome(report: FactorFalsificationReport) -> str:
    if report.falsified:
        return "rejected"
    if report.conclusion_cap == ConclusionLevel.research_candidate:
        return "selected"
    return "reported"


def _clean_metric_values(values: object) -> list[float]:
    output: list[float] = []
    for value in values:
        if value is None:
            continue
        number = float(value)
        if math.isnan(number):
            continue
        output.append(number)
    return output


def _icir(values: list[float]) -> float | None:
    if not values:
        return None
    std = float(np.std(values, ddof=1)) if len(values) > 1 else 0.0
    mean = float(np.mean(values))
    if std == 0.0:
        return 999.0 if mean > 0 else 0.0
    return mean / std


def _t_stat(values: list[float]) -> float | None:
    if not values:
        return None
    std = float(np.std(values, ddof=1)) if len(values) > 1 else 0.0
    mean = float(np.mean(values))
    if std == 0.0:
        if mean > 0:
            return 999.0
        if mean < 0:
            return -999.0
        return 0.0
    return mean / (std / math.sqrt(len(values)))


def _dedupe_failures(failures: list[HardFailureCode]) -> list[HardFailureCode]:
    output: list[HardFailureCode] = []
    for failure in failures:
        if failure not in output:
            output.append(failure)
    return output


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)

