"""A-share tradability mask fixtures and report contract."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field


class TradabilityMaskReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "2.1.0"
    report_id: str
    as_of: date
    universe_size: int
    tradable_count: int
    masks: dict[str, dict[str, bool]]
    mask_policy: dict[str, str]
    st_mask_policy: dict[str, str]
    new_stock_policy: dict[str, str]
    limit_state_policy: dict[str, str]
    suspension_policy: dict[str, str]
    lot_size_policy: str = "100_shares"
    data_audit_refs: list[str]
    warnings: list[str] = Field(default_factory=list)


def build_tradability_mask(
    frame: pd.DataFrame,
    *,
    as_of: date,
    new_stock_min_age_days: int = 60,
    one_word_volume_ratio: float = 0.05,
) -> TradabilityMaskReport:
    masks: dict[str, dict[str, bool]] = {}
    for row in frame.to_dict(orient="records"):
        symbol = str(row["symbol"])
        limit_up_pass = not _is_limit_up(row)
        suspension_pass = not bool(row.get("is_suspended", False))
        st_pass = not _is_st_effective(row, as_of)
        new_stock_pass = _is_old_enough(row, as_of, new_stock_min_age_days)
        one_word_pass = not _is_one_word_board(row, one_word_volume_ratio)
        lot_pass = True
        tradable = all([limit_up_pass, suspension_pass, st_pass, new_stock_pass, one_word_pass, lot_pass])
        masks[symbol] = {
            "limit_up": limit_up_pass,
            "suspension": suspension_pass,
            "st": st_pass,
            "new_stock": new_stock_pass,
            "one_word_board": one_word_pass,
            "lot_size": lot_pass,
            "tradable": tradable,
        }

    return TradabilityMaskReport(
        report_id=f"tradability-{as_of.isoformat()}",
        as_of=as_of,
        universe_size=len(masks),
        tradable_count=sum(1 for mask in masks.values() if mask["tradable"]),
        masks=masks,
        mask_policy={
            "tradable": "all individual masks must pass",
            "execution_universe": "exclude non-tradable A-share states",
        },
        st_mask_policy={"announcement_after_close": "effective next day"},
        new_stock_policy={"min_age_days": str(new_stock_min_age_days)},
        limit_state_policy={"limit_up": "cannot buy when close reaches limit_up_price"},
        suspension_policy={"is_suspended": "exclude from signal and execution universe"},
        data_audit_refs=["fixture-tradability-audit"],
    )


def _is_limit_up(row: dict[str, Any]) -> bool:
    close = float(row.get("close", 0.0))
    limit_up_price = float(row.get("limit_up_price", float("inf")))
    return close >= limit_up_price


def _is_one_word_board(row: dict[str, Any], max_volume_ratio: float) -> bool:
    open_ = float(row.get("open", 0.0))
    high = float(row.get("high", 0.0))
    low = float(row.get("low", 0.0))
    close = float(row.get("close", 0.0))
    limit_up_price = float(row.get("limit_up_price", float("inf")))
    volume = float(row.get("volume", 0.0))
    avg_volume_20 = float(row.get("avg_volume_20", 1.0)) or 1.0
    return (
        open_ == high == low == close == limit_up_price
        and volume / avg_volume_20 < max_volume_ratio
    )


def _is_st_effective(row: dict[str, Any], as_of: date) -> bool:
    raw = row.get("st_announcement_date")
    if raw is None or pd.isna(raw):
        return False
    announcement_date = pd.Timestamp(raw).date()
    effective_date = announcement_date
    if bool(row.get("st_announcement_after_close", False)):
        effective_date = announcement_date + timedelta(days=1)
    return as_of >= effective_date


def _is_old_enough(row: dict[str, Any], as_of: date, min_age_days: int) -> bool:
    raw = row.get("listing_date")
    if raw is None or pd.isna(raw):
        return False
    listing_date = pd.Timestamp(raw).date()
    return (as_of - listing_date).days >= min_age_days

