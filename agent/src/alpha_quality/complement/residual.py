"""Date-aligned ridge residual IC evidence for ComplementEvidence.v2."""

from __future__ import annotations

from typing import Mapping, cast

import numpy as np
import pandas as pd

from src.alpha_quality.complement.model import ComplementPolicy, ResidualComplementEvidence
from src.alpha_quality.ic_metrics import compute_ic_metrics
from src.research_ledger.hash_utils import canonical_json_hash


def _unavailable(
    policy: ComplementPolicy,
    *,
    availability: str,
    reason: str,
    effective_dates: int = 0,
) -> ResidualComplementEvidence:
    content: dict[str, object] = {
        "schema_version": "residual_complement_evidence.v2",
        "availability": availability,
        "ridge_alpha": policy.ridge_alpha,
        "solver": "not_run",
        "effective_dates": effective_dates,
        "rank_ic_mean": None,
        "rank_ic_std": None,
        "rank_icir": None,
        "t_stat": None,
        "uncertainty_method": None,
        "reason_code": reason,
    }
    return ResidualComplementEvidence(
        schema_version="residual_complement_evidence.v2",
        availability=availability,  # type: ignore[arg-type]
        ridge_alpha=policy.ridge_alpha,
        solver="not_run",
        effective_dates=effective_dates,
        rank_ic_mean=None,
        rank_ic_std=None,
        rank_icir=None,
        t_stat=None,
        uncertainty_method=None,
        reason_code=reason,
        evidence_hash=canonical_json_hash(content),
    )


def compute_residual_complement(
    *,
    candidate_panel: pd.DataFrame | None,
    reference_panels: Mapping[str, pd.DataFrame] | None,
    forward_returns: pd.DataFrame | None,
    valid_mask: pd.DataFrame | None,
    policy: ComplementPolicy,
    horizon: int = 1,
) -> ResidualComplementEvidence:
    if candidate_panel is None or forward_returns is None or valid_mask is None:
        return _unavailable(
            policy,
            availability="unavailable",
            reason="RESIDUAL_REQUIRED_INPUT_MISSING",
        )
    if reference_panels is None or not reference_panels:
        return _unavailable(
            policy,
            availability="unavailable",
            reason="RESIDUAL_REFERENCE_POOL_EMPTY",
        )
    dates = candidate_panel.index.intersection(forward_returns.index).intersection(valid_mask.index)
    symbols = candidate_panel.columns.intersection(forward_returns.columns).intersection(valid_mask.columns)
    if dates.empty or symbols.empty:
        return _unavailable(
            policy,
            availability="insufficient",
            reason="RESIDUAL_ALIGNMENT_EMPTY",
        )
    residual_panel = pd.DataFrame(np.nan, index=dates, columns=symbols, dtype=float)
    residual_mask = pd.DataFrame(False, index=dates, columns=symbols, dtype=bool)
    ordered_references = tuple(sorted(reference_panels.items()))
    effective_dates = 0
    for date in dates:
        candidate_row = cast(pd.Series, candidate_panel.loc[date, symbols])
        return_row = cast(pd.Series, forward_returns.loc[date, symbols])
        mask_row = cast(pd.Series, valid_mask.loc[date, symbols]).fillna(False).astype(bool)
        columns: dict[str, pd.Series] = {
            "candidate": candidate_row,
            "forward_return": return_row,
        }
        for factor_spec_id, panel in ordered_references:
            if date not in panel.index:
                columns = {}
                break
            columns[factor_spec_id] = cast(pd.Series, panel.reindex(columns=symbols).loc[date])
        if not columns:
            continue
        aligned = pd.DataFrame(columns).loc[mask_row].dropna()
        if len(aligned) < policy.minimum_cross_section:
            continue
        candidate_rank = aligned["candidate"].rank(method="average", pct=True).to_numpy(dtype=float)
        candidate_rank -= candidate_rank.mean()
        design_columns: list[np.ndarray] = []
        for factor_spec_id, _ in ordered_references:
            ranked = aligned[factor_spec_id].rank(method="average", pct=True).to_numpy(dtype=float)
            ranked -= ranked.mean()
            if float(np.dot(ranked, ranked)) > 0.0:
                design_columns.append(ranked)
        if not design_columns or float(np.dot(candidate_rank, candidate_rank)) <= 0.0:
            continue
        design = np.column_stack(design_columns)
        gram = design.T @ design
        penalty = policy.ridge_alpha * np.eye(gram.shape[0], dtype=float)
        coefficients = np.linalg.solve(gram + penalty, design.T @ candidate_rank)
        residual = candidate_rank - design @ coefficients
        if not np.isfinite(residual).all() or float(np.dot(residual, residual)) <= 0.0:
            continue
        residual_panel.loc[date, aligned.index] = residual
        residual_mask.loc[date, aligned.index] = True
        effective_dates += 1
    if effective_dates < policy.minimum_effective_dates:
        return _unavailable(
            policy,
            availability="insufficient",
            reason="RESIDUAL_EFFECTIVE_DATES_INSUFFICIENT",
            effective_dates=effective_dates,
        )
    metrics = compute_ic_metrics(
        residual_panel,
        forward_returns.loc[dates, symbols],
        horizon=horizon,
        valid_mask=residual_mask,
        min_cross_section=policy.minimum_cross_section,
    )
    if metrics.n_obs < policy.minimum_effective_dates or any(
        value is None
        for value in (metrics.rank_ic_mean, metrics.rank_ic_std, metrics.rank_icir, metrics.t_stat)
    ):
        return _unavailable(
            policy,
            availability="insufficient",
            reason="RESIDUAL_IC_INSUFFICIENT",
            effective_dates=metrics.n_obs,
        )
    content: dict[str, object] = {
        "schema_version": "residual_complement_evidence.v2",
        "availability": "available",
        "ridge_alpha": policy.ridge_alpha,
        "solver": "date_wise_ridge",
        "effective_dates": metrics.n_obs,
        "rank_ic_mean": metrics.rank_ic_mean,
        "rank_ic_std": metrics.rank_ic_std,
        "rank_icir": metrics.rank_icir,
        "t_stat": metrics.t_stat,
        "uncertainty_method": metrics.t_stat_method,
        "reason_code": None,
    }
    return ResidualComplementEvidence(
        schema_version="residual_complement_evidence.v2",
        availability="available",
        ridge_alpha=policy.ridge_alpha,
        solver="date_wise_ridge",
        effective_dates=metrics.n_obs,
        rank_ic_mean=metrics.rank_ic_mean,
        rank_ic_std=metrics.rank_ic_std,
        rank_icir=metrics.rank_icir,
        t_stat=metrics.t_stat,
        uncertainty_method=metrics.t_stat_method,
        reason_code=None,
        evidence_hash=canonical_json_hash(content),
    )


__all__ = ["compute_residual_complement"]
