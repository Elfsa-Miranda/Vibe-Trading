"""Frozen net portfolio marginal-value evidence."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from src.alpha_quality.complement.model import ComplementPolicy, PortfolioComplementEvidence
from src.research_ledger.hash_utils import canonical_json_hash


def _information_ratio(series: pd.Series, annualization_factor: int) -> float:
    values = series.to_numpy(dtype=float)
    if len(values) < 2:
        return 0.0
    standard_deviation = float(np.std(values, ddof=1))
    if not math.isfinite(standard_deviation) or standard_deviation <= 0.0:
        return 0.0
    return float(np.mean(values) / standard_deviation * math.sqrt(annualization_factor))


def _max_drawdown(series: pd.Series) -> float:
    nav = (1.0 + series.astype(float)).cumprod()
    if nav.empty:
        return 0.0
    return float((nav / nav.cummax() - 1.0).min())


def _unavailable(
    policy: ComplementPolicy,
    *,
    availability: str,
    reason: str,
    effective_dates: int = 0,
) -> PortfolioComplementEvidence:
    content: dict[str, object] = {
        "schema_version": "portfolio_complement_evidence.v2",
        "availability": availability,
        "effective_dates": effective_dates,
        "candidate_allocation": policy.candidate_allocation,
        "net_return_mean_before": None,
        "net_return_mean_after": None,
        "delta_net_return_mean": None,
        "information_ratio_before": None,
        "information_ratio_after": None,
        "delta_information_ratio": None,
        "max_drawdown_before": None,
        "max_drawdown_after": None,
        "delta_max_drawdown": None,
        "turnover_before": None,
        "turnover_after": None,
        "delta_turnover": None,
        "candidate_cost_bps_mean": None,
        "candidate_capacity_scale_mean": None,
        "candidate_exposure_penalty_mean": None,
        "delta_ir_interval": None,
        "uncertainty_method": None,
        "reason_code": reason,
    }
    return PortfolioComplementEvidence(
        schema_version="portfolio_complement_evidence.v2",
        availability=availability,  # type: ignore[arg-type]
        effective_dates=effective_dates,
        candidate_allocation=policy.candidate_allocation,
        net_return_mean_before=None,
        net_return_mean_after=None,
        delta_net_return_mean=None,
        information_ratio_before=None,
        information_ratio_after=None,
        delta_information_ratio=None,
        max_drawdown_before=None,
        max_drawdown_after=None,
        delta_max_drawdown=None,
        turnover_before=None,
        turnover_after=None,
        delta_turnover=None,
        candidate_cost_bps_mean=None,
        candidate_capacity_scale_mean=None,
        candidate_exposure_penalty_mean=None,
        delta_ir_interval=None,
        uncertainty_method=None,
        reason_code=reason,
        evidence_hash=canonical_json_hash(content),
    )


def _moving_block_delta_ir_interval(
    before: pd.Series,
    after: pd.Series,
    *,
    policy: ComplementPolicy,
) -> tuple[float, float]:
    n = len(before)
    block_length = min(policy.bootstrap_block_length, n)
    rng = np.random.default_rng(policy.bootstrap_seed)
    before_values = before.to_numpy(dtype=float)
    after_values = after.to_numpy(dtype=float)
    deltas: list[float] = []
    blocks_needed = math.ceil(n / block_length)
    for _ in range(policy.bootstrap_samples):
        indices: list[int] = []
        for _ in range(blocks_needed):
            start = int(rng.integers(0, n))
            indices.extend((start + offset) % n for offset in range(block_length))
        selected = np.asarray(indices[:n], dtype=int)
        before_sample = pd.Series(before_values[selected])
        after_sample = pd.Series(after_values[selected])
        deltas.append(
            _information_ratio(after_sample, policy.annualization_factor)
            - _information_ratio(before_sample, policy.annualization_factor)
        )
    lower, upper = np.quantile(np.asarray(deltas, dtype=float), [0.025, 0.975])
    return float(lower), float(upper)


def compute_portfolio_complement(
    *,
    pool_net_returns: pd.Series | None,
    candidate_gross_returns: pd.Series | None,
    pool_turnover: pd.Series | None,
    candidate_turnover: pd.Series | None,
    candidate_cost_bps: pd.Series | None,
    candidate_capacity_scale: pd.Series | None,
    candidate_exposure_penalty: pd.Series | None,
    policy: ComplementPolicy,
) -> PortfolioComplementEvidence:
    required = {
        "pool_net_returns": pool_net_returns,
        "candidate_gross_returns": candidate_gross_returns,
        "pool_turnover": pool_turnover,
        "candidate_turnover": candidate_turnover,
    }
    if policy.require_execution_evidence:
        required["candidate_cost_bps"] = candidate_cost_bps
    if policy.require_capacity_evidence:
        required["candidate_capacity_scale"] = candidate_capacity_scale
    if policy.require_exposure_evidence:
        required["candidate_exposure_penalty"] = candidate_exposure_penalty
    missing = sorted(name for name, value in required.items() if value is None)
    if missing:
        return _unavailable(
            policy,
            availability="unavailable",
            reason="PORTFOLIO_REQUIRED_EVIDENCE_MISSING",
        )
    assert pool_net_returns is not None
    assert candidate_gross_returns is not None
    assert pool_turnover is not None
    assert candidate_turnover is not None
    series = {
        "pool_net": pool_net_returns,
        "candidate_gross": candidate_gross_returns,
        "pool_turnover": pool_turnover,
        "candidate_turnover": candidate_turnover,
        "candidate_cost_bps": candidate_cost_bps
        if candidate_cost_bps is not None
        else pd.Series(0.0, index=candidate_gross_returns.index),
        "capacity_scale": candidate_capacity_scale
        if candidate_capacity_scale is not None
        else pd.Series(1.0, index=candidate_gross_returns.index),
        "exposure_penalty": candidate_exposure_penalty
        if candidate_exposure_penalty is not None
        else pd.Series(0.0, index=candidate_gross_returns.index),
    }
    aligned = pd.concat(series, axis=1, join="inner").dropna()
    if len(aligned) < policy.minimum_effective_dates:
        return _unavailable(
            policy,
            availability="insufficient",
            reason="PORTFOLIO_EFFECTIVE_DATES_INSUFFICIENT",
            effective_dates=len(aligned),
        )
    values = aligned.to_numpy(dtype=float)
    if not np.isfinite(values).all():
        return _unavailable(
            policy,
            availability="unavailable",
            reason="PORTFOLIO_NONFINITE_EVIDENCE",
        )
    if ((aligned["capacity_scale"] < 0.0) | (aligned["capacity_scale"] > 1.0)).any():
        return _unavailable(
            policy,
            availability="unavailable",
            reason="CAPACITY_SCALE_OUT_OF_RANGE",
        )
    candidate_net = (
        aligned["candidate_gross"] * aligned["capacity_scale"]
        - aligned["candidate_cost_bps"] / 10_000.0
        - aligned["exposure_penalty"]
    )
    allocation = policy.candidate_allocation
    before = aligned["pool_net"].astype(float)
    after = (1.0 - allocation) * before + allocation * candidate_net
    turnover_before = aligned["pool_turnover"].astype(float)
    turnover_after = (
        (1.0 - allocation) * turnover_before
        + allocation * aligned["candidate_turnover"].astype(float)
    )
    before_ir = _information_ratio(before, policy.annualization_factor)
    after_ir = _information_ratio(after, policy.annualization_factor)
    before_drawdown = _max_drawdown(before)
    after_drawdown = _max_drawdown(after)
    interval = _moving_block_delta_ir_interval(before, after, policy=policy)
    content: dict[str, object] = {
        "schema_version": "portfolio_complement_evidence.v2",
        "availability": "available",
        "effective_dates": len(aligned),
        "candidate_allocation": allocation,
        "net_return_mean_before": float(before.mean()),
        "net_return_mean_after": float(after.mean()),
        "delta_net_return_mean": float(after.mean() - before.mean()),
        "information_ratio_before": before_ir,
        "information_ratio_after": after_ir,
        "delta_information_ratio": after_ir - before_ir,
        "max_drawdown_before": before_drawdown,
        "max_drawdown_after": after_drawdown,
        "delta_max_drawdown": after_drawdown - before_drawdown,
        "turnover_before": float(turnover_before.mean()),
        "turnover_after": float(turnover_after.mean()),
        "delta_turnover": float(turnover_after.mean() - turnover_before.mean()),
        "candidate_cost_bps_mean": float(aligned["candidate_cost_bps"].mean()),
        "candidate_capacity_scale_mean": float(aligned["capacity_scale"].mean()),
        "candidate_exposure_penalty_mean": float(aligned["exposure_penalty"].mean()),
        "delta_ir_interval": list(interval),
        "uncertainty_method": "seeded_circular_moving_block_bootstrap.v1",
        "reason_code": None,
    }
    return PortfolioComplementEvidence(
        schema_version="portfolio_complement_evidence.v2",
        availability="available",
        effective_dates=len(aligned),
        candidate_allocation=allocation,
        net_return_mean_before=float(before.mean()),
        net_return_mean_after=float(after.mean()),
        delta_net_return_mean=float(after.mean() - before.mean()),
        information_ratio_before=before_ir,
        information_ratio_after=after_ir,
        delta_information_ratio=after_ir - before_ir,
        max_drawdown_before=before_drawdown,
        max_drawdown_after=after_drawdown,
        delta_max_drawdown=after_drawdown - before_drawdown,
        turnover_before=float(turnover_before.mean()),
        turnover_after=float(turnover_after.mean()),
        delta_turnover=float(turnover_after.mean() - turnover_before.mean()),
        candidate_cost_bps_mean=float(aligned["candidate_cost_bps"].mean()),
        candidate_capacity_scale_mean=float(aligned["capacity_scale"].mean()),
        candidate_exposure_penalty_mean=float(aligned["exposure_penalty"].mean()),
        delta_ir_interval=interval,
        uncertainty_method="seeded_circular_moving_block_bootstrap.v1",
        reason_code=None,
        evidence_hash=canonical_json_hash(content),
    )


__all__ = ["compute_portfolio_complement"]
