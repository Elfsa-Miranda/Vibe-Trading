"""Trading-day alignment helpers."""

from __future__ import annotations

import pandas as pd


def add_trading_days(start: pd.Timestamp, n: int, trading_days: pd.DatetimeIndex | list[pd.Timestamp]) -> pd.Timestamp:
    days = pd.DatetimeIndex(trading_days).sort_values()
    start = pd.Timestamp(start).normalize()
    try:
        idx = days.get_loc(start)
    except KeyError as exc:
        raise ValueError(f"start date {start.date()} is not in trading calendar") from exc
    target = idx + n
    if target < 0 or target >= len(days):
        raise ValueError("target trading day outside calendar")
    return pd.Timestamp(days[target])

