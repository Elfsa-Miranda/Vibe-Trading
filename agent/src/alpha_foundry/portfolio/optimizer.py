"""Constrained long-only top-N portfolio MVP."""

from __future__ import annotations

from typing import Any

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from src.alpha_foundry.common.errors import HardFailureCode


class PortfolioConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "2.1.0"
    top_n: int
    single_name_cap: float
    sector_cap: float
    turnover_cap: float
    adv_cap: float
    benchmark_id: str | None = "CSI_500_EW"
    portfolio_notional: float = 1_000_000.0
    lot_size: int = 100


class PortfolioConstructionReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "2.1.0"
    report_id: str
    weights: dict[str, float]
    shares: dict[str, int]
    sector_weights: dict[str, float]
    turnover: float | None = None
    adv_participation: dict[str, float] = Field(default_factory=dict)
    constraints: dict[str, Any]
    hard_failures: list[HardFailureCode] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def construct_long_only_top_n_portfolio(
    scores: pd.DataFrame,
    *,
    constraints: PortfolioConstraints,
    previous_weights: dict[str, float] | None = None,
) -> PortfolioConstructionReport:
    hard_failures: list[HardFailureCode] = []
    warnings = ["optimizer_mvp_not_production"]
    if constraints.benchmark_id is None:
        hard_failures.append(HardFailureCode.BENCHMARK_MISSING)

    required = {"symbol", "score", "sector", "adv", "price"}
    missing = sorted(required - set(scores.columns))
    if missing:
        raise ValueError(f"score frame missing required columns: {missing}")

    selected = scores.sort_values("score", ascending=False).head(constraints.top_n).copy()
    if selected.empty:
        return PortfolioConstructionReport(
            report_id="portfolio-empty",
            weights={},
            shares={},
            sector_weights={},
            turnover=0.0,
            constraints=constraints.model_dump(mode="json"),
            hard_failures=hard_failures,
            warnings=warnings,
        )

    raw_weight = min(1.0 / len(selected), constraints.single_name_cap)
    selected["weight"] = raw_weight
    selected = _apply_sector_cap(selected, constraints.sector_cap)
    selected = _apply_adv_cap(selected, constraints)
    selected = _apply_lot_size(selected, constraints)

    weights = {str(row.symbol): float(row.weight) for row in selected.itertuples()}
    shares = {str(row.symbol): int(row.shares) for row in selected.itertuples()}
    sector_weights = {
        str(sector): float(group["weight"].sum()) for sector, group in selected.groupby("sector", sort=True)
    }
    turnover = _turnover(weights, previous_weights or {})
    if turnover > constraints.turnover_cap:
        scale = constraints.turnover_cap / turnover if turnover else 1.0
        weights = {symbol: weight * scale for symbol, weight in weights.items()}
        turnover = _turnover(weights, previous_weights or {})
        warnings.append("turnover_scaled_to_cap")

    adv_participation = {
        str(row.symbol): float((weights.get(str(row.symbol), 0.0) * constraints.portfolio_notional) / row.adv)
        for row in selected.itertuples()
    }

    return PortfolioConstructionReport(
        report_id="portfolio-long-only-top-n",
        weights=weights,
        shares=shares,
        sector_weights=sector_weights,
        turnover=turnover,
        adv_participation=adv_participation,
        constraints=constraints.model_dump(mode="json"),
        hard_failures=hard_failures,
        warnings=warnings,
    )


def _apply_sector_cap(selected: pd.DataFrame, sector_cap: float) -> pd.DataFrame:
    adjusted = selected.copy()
    for sector, group in adjusted.groupby("sector"):
        total = float(group["weight"].sum())
        if total > sector_cap:
            scale = sector_cap / total
            adjusted.loc[group.index, "weight"] = group["weight"] * scale
    return adjusted


def _apply_adv_cap(selected: pd.DataFrame, constraints: PortfolioConstraints) -> pd.DataFrame:
    adjusted = selected.copy()
    max_weight_by_adv = constraints.adv_cap * adjusted["adv"].astype(float) / constraints.portfolio_notional
    adjusted["weight"] = adjusted["weight"].clip(upper=max_weight_by_adv)
    return adjusted


def _apply_lot_size(selected: pd.DataFrame, constraints: PortfolioConstraints) -> pd.DataFrame:
    adjusted = selected.copy()
    raw_shares = adjusted["weight"] * constraints.portfolio_notional / adjusted["price"].astype(float)
    adjusted["shares"] = (raw_shares // constraints.lot_size).astype(int) * constraints.lot_size
    adjusted["weight"] = adjusted["shares"] * adjusted["price"].astype(float) / constraints.portfolio_notional
    return adjusted


def _turnover(weights: dict[str, float], previous: dict[str, float]) -> float:
    symbols = set(weights) | set(previous)
    return sum(abs(weights.get(symbol, 0.0) - previous.get(symbol, 0.0)) for symbol in symbols) / 2.0

