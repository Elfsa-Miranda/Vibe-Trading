"""Factor turnover diagnostics."""

from __future__ import annotations

import pandas as pd

from src.alpha_foundry.panels.interfaces import validate_factor_output_frame


def compute_factor_turnover(factor_frame: pd.DataFrame) -> float | None:
    frame = validate_factor_output_frame(factor_frame).copy()
    frame["date"] = pd.to_datetime(frame["date"]).dt.normalize()
    ranks = frame.sort_values(["symbol", "date"]).copy()
    ranks["rank"] = ranks.groupby("date")["factor_value"].rank(pct=True)
    ranks["prev_rank"] = ranks.groupby("symbol")["rank"].shift(1)
    diffs = (ranks["rank"] - ranks["prev_rank"]).abs().dropna()
    if diffs.empty:
        return None
    return float(diffs.mean())

