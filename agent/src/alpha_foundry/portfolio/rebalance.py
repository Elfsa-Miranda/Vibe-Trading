"""A-share T+1 rebalance feasibility checks."""

from __future__ import annotations

import pandas as pd
from pydantic import BaseModel, ConfigDict


class T1ConstraintViolation(ValueError):
    """Raised when a rebalance attempts same-day buy and sell of the same symbol."""


class RebalanceFeasibilityReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "2.1.0"
    t_plus_one_feasible: bool
    buy_turnover: float
    sell_turnover: float


def check_t1_rebalance_feasibility(trades: pd.DataFrame) -> RebalanceFeasibilityReport:
    required = {"date", "symbol", "side", "shares"}
    missing = sorted(required - set(trades.columns))
    if missing:
        raise ValueError(f"trades frame missing required columns: {missing}")
    frame = trades.copy()
    frame["date"] = pd.to_datetime(frame["date"]).dt.normalize()
    frame["side"] = frame["side"].astype(str).str.lower()

    grouped = frame.groupby(["date", "symbol"])["side"].agg(set)
    for (day, symbol), sides in grouped.items():
        if {"buy", "sell"}.issubset(sides):
            raise T1ConstraintViolation(f"same-day buy and sell violates T+1: {symbol} on {day.date()}")

    notional = frame["notional"] if "notional" in frame.columns else frame["shares"].astype(float)
    buy_turnover = float(notional[frame["side"] == "buy"].sum())
    sell_turnover = float(notional[frame["side"] == "sell"].sum())
    return RebalanceFeasibilityReport(
        t_plus_one_feasible=True,
        buy_turnover=buy_turnover,
        sell_turnover=sell_turnover,
    )

