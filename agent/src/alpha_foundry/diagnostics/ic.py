"""IC and Rank IC diagnostics for Alpha Foundry factors."""

from __future__ import annotations

import math

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from src.alpha_foundry.panels.interfaces import validate_factor_output_frame


class ICSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "2.1.0"
    return_column: str
    ic_by_date: dict[str, float | None] = Field(default_factory=dict)
    rank_ic_by_date: dict[str, float | None] = Field(default_factory=dict)
    ic_raw: float | None = None
    rank_ic_raw: float | None = None
    observation_count: int = 0


def join_factor_forward_returns(
    factor_frame: pd.DataFrame,
    forward_returns: pd.DataFrame,
    *,
    return_column: str,
) -> pd.DataFrame:
    clean_factor = validate_factor_output_frame(factor_frame)
    required = {"date", "symbol", return_column}
    missing = sorted(required - set(forward_returns.columns))
    if missing:
        raise ValueError(f"forward return frame missing required columns: {missing}")

    returns = forward_returns.loc[:, ["date", "symbol", return_column]].copy()
    returns["date"] = pd.to_datetime(returns["date"]).dt.normalize()
    factor = clean_factor.copy()
    factor["date"] = pd.to_datetime(factor["date"]).dt.normalize()
    return factor.merge(returns, on=["date", "symbol"], how="inner")


def compute_ic_summary(
    factor_frame: pd.DataFrame,
    forward_returns: pd.DataFrame,
    *,
    return_column: str,
) -> ICSummary:
    joined = join_factor_forward_returns(factor_frame, forward_returns, return_column=return_column)
    ic_by_date: dict[str, float | None] = {}
    rank_ic_by_date: dict[str, float | None] = {}

    for day, group in joined.groupby("date", sort=True):
        ic_by_date[pd.Timestamp(day).date().isoformat()] = _safe_corr(group["factor_value"], group[return_column])
        rank_ic_by_date[pd.Timestamp(day).date().isoformat()] = _safe_corr(
            group["factor_value"].rank(method="average"),
            group[return_column].rank(method="average"),
        )

    return ICSummary(
        return_column=return_column,
        ic_by_date=ic_by_date,
        rank_ic_by_date=rank_ic_by_date,
        ic_raw=_mean_non_null(ic_by_date.values()),
        rank_ic_raw=_mean_non_null(rank_ic_by_date.values()),
        observation_count=len(joined),
    )


def _safe_corr(left: pd.Series, right: pd.Series) -> float | None:
    if len(left) < 2 or left.nunique(dropna=True) < 2 or right.nunique(dropna=True) < 2:
        return 0.0
    value = float(left.astype(float).corr(right.astype(float)))
    if math.isnan(value):
        return 0.0
    return value


def _mean_non_null(values: object) -> float | None:
    clean = [float(value) for value in values if value is not None and not math.isnan(float(value))]
    if not clean:
        return None
    return float(sum(clean) / len(clean))

