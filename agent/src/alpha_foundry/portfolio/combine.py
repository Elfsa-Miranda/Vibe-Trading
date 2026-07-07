"""Orthogonal alpha combination diagnostics."""

from __future__ import annotations

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field


class OrthogonalAlphaReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "2.1.0"
    report_id: str
    candidate_factor_id: str
    max_abs_correlation: float
    marginal_ic_after_existing: float | None = None
    correlation_cap: float = 0.65
    orthogonalization_required_above: float = 0.50
    orthogonalization_required: bool
    accepted: bool
    warnings: list[str] = Field(default_factory=list)


def assess_orthogonal_alpha(
    frame: pd.DataFrame,
    *,
    candidate_column: str,
    existing_factor_columns: list[str],
    marginal_ic_after_existing: float | None,
    correlation_cap: float = 0.65,
    orthogonalization_required_above: float = 0.50,
) -> OrthogonalAlphaReport:
    correlations = [
        abs(float(frame[candidate_column].astype(float).corr(frame[column].astype(float))))
        for column in existing_factor_columns
    ]
    max_corr = max(correlations) if correlations else 0.0
    orthogonalization_required = max_corr > orthogonalization_required_above
    warnings: list[str] = []
    accepted = True
    if max_corr > correlation_cap and (marginal_ic_after_existing is None or marginal_ic_after_existing <= 0.0):
        warnings.append("high_correlation_no_marginal_ic")
        accepted = False
    elif orthogonalization_required:
        warnings.append("orthogonalization_required_above_0.50")

    return OrthogonalAlphaReport(
        report_id=f"orthogonal-alpha-{candidate_column}",
        candidate_factor_id=candidate_column,
        max_abs_correlation=max_corr,
        marginal_ic_after_existing=marginal_ic_after_existing,
        correlation_cap=correlation_cap,
        orthogonalization_required_above=orthogonalization_required_above,
        orthogonalization_required=orthogonalization_required,
        accepted=accepted,
        warnings=warnings,
    )

