"""Limit and liquidity mechanism factors for A-share alpha foundry."""

from __future__ import annotations

from datetime import date
from typing import Iterable

import pandas as pd
from pydantic import BaseModel, ConfigDict

from src.alpha_foundry.common.errors import ConclusionLevel
from src.alpha_foundry.factors.base import FactorSpec, factor_definition_hash, load_factor_specs
from src.alpha_foundry.panels.interfaces import FACTOR_OUTPUT_COLUMNS, validate_factor_output_frame
from src.alpha_foundry.panels.tradability import build_tradability_mask


LIMIT_LIQUIDITY_SPECS = tuple(load_factor_specs("limit_liquidity"))
LIMIT_LIQUIDITY_SPEC_BY_ID = {spec.factor_id: spec for spec in LIMIT_LIQUIDITY_SPECS}
LIMIT_LIQUIDITY_FACTOR_IDS = tuple(spec.factor_id for spec in LIMIT_LIQUIDITY_SPECS)


class FactorInputFrameError(ValueError):
    """Raised when factor inputs violate formula contracts."""


class LimitLiquidityFactorMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "2.1.0"
    factor_id: str
    conclusion_cap: ConclusionLevel
    exploratory_only: bool
    proxy_note: str | None = None
    can_claim_level2_queue_alpha: bool = False
    standalone_alpha_claim_allowed: bool = True
    signal_time: str
    data_availability_policy: str
    factor_definition_hash: str


def get_limit_liquidity_factor_metadata(
    factor_id: str,
    *,
    level2_available: bool = False,
) -> LimitLiquidityFactorMetadata:
    spec = _get_spec(factor_id)
    is_queue_proxy = factor_id == "limit_queue_pressure_proxy"
    is_one_word_mask = factor_id == "one_word_board_exclusion_alpha"
    return LimitLiquidityFactorMetadata(
        factor_id=factor_id,
        conclusion_cap=spec.conclusion_cap,
        exploratory_only=not level2_available or spec.conclusion_cap == ConclusionLevel.exploratory,
        proxy_note=spec.formula.proxy_note,
        can_claim_level2_queue_alpha=is_queue_proxy and level2_available,
        standalone_alpha_claim_allowed=not is_one_word_mask,
        signal_time=spec.formula.signal_time,
        data_availability_policy=spec.formula.data_availability_policy,
        factor_definition_hash=factor_definition_hash(spec),
    )


def get_limit_liquidity_specs() -> dict[str, FactorSpec]:
    return dict(LIMIT_LIQUIDITY_SPEC_BY_ID)


def compute_limit_liquidity_factors(
    frame: pd.DataFrame,
    *,
    factor_ids: Iterable[str] | None = None,
    level2_available: bool = False,
) -> dict[str, pd.DataFrame]:
    ids = tuple(factor_ids) if factor_ids is not None else LIMIT_LIQUIDITY_FACTOR_IDS
    return {
        factor_id: compute_limit_liquidity_factor(frame, factor_id, level2_available=level2_available)
        for factor_id in ids
    }


def compute_limit_liquidity_factor(
    frame: pd.DataFrame,
    factor_id: str,
    *,
    as_of: pd.Timestamp | None = None,
    available_at: pd.Timestamp | None = None,
    level2_available: bool = False,
    one_word_volume_ratio: float = 0.05,
) -> pd.DataFrame:
    spec = _get_spec(factor_id)
    prepared = _prepare_input_frame(frame, spec)

    if factor_id == "limit_lock_strength":
        values = _limit_lock_strength(prepared)
    elif factor_id == "limit_lock_persistence":
        values = _limit_lock_persistence(prepared)
    elif factor_id == "failed_limit_breakout_reversal":
        values = _failed_limit_breakout_reversal(prepared)
    elif factor_id == "post_limit_opening_pressure":
        values = _post_limit_opening_pressure(prepared)
    elif factor_id == "one_word_board_exclusion_alpha":
        values = _one_word_board_exclusion(prepared, one_word_volume_ratio)
    elif factor_id == "limit_gap_decay":
        values = _limit_gap_decay(prepared)
    elif factor_id == "limit_down_liquidity_recovery":
        values = _limit_down_liquidity_recovery(prepared)
    elif factor_id == "limit_queue_pressure_proxy":
        values = _limit_queue_pressure_proxy(prepared, level2_available=level2_available)
    else:
        raise FactorInputFrameError(f"unsupported factor_id: {factor_id}")

    return _build_factor_output(
        prepared,
        factor_id=factor_id,
        factor_value=values,
        as_of=as_of,
        available_at=available_at,
    )


def build_limit_liquidity_execution_mask(frame: pd.DataFrame, *, as_of: date) -> dict[str, bool]:
    prepared = frame.copy()
    if "date" in prepared.columns:
        prepared["date"] = pd.to_datetime(prepared["date"])
        prepared = prepared[prepared["date"] == pd.Timestamp(as_of)].copy()
    report = build_tradability_mask(prepared.reset_index(drop=True), as_of=as_of)
    return {symbol: bool(mask["tradable"]) for symbol, mask in report.masks.items()}


def _get_spec(factor_id: str) -> FactorSpec:
    try:
        return LIMIT_LIQUIDITY_SPEC_BY_ID[factor_id]
    except KeyError as exc:
        raise FactorInputFrameError(f"unknown factor_id: {factor_id}") from exc


def _prepare_input_frame(frame: pd.DataFrame, spec: FactorSpec) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame):
        raise FactorInputFrameError("factor input must be a pandas DataFrame")

    forbidden = [
        col
        for col in frame.columns
        if col in spec.formula.forbidden_fields or col.startswith("future_")
    ]
    if forbidden:
        raise FactorInputFrameError(f"factor input contains forbidden columns: {forbidden}")

    required = {"date", "symbol", *spec.formula.required_fields}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise FactorInputFrameError(f"factor input missing required columns: {missing}")

    prepared = frame.copy()
    prepared["date"] = pd.to_datetime(prepared["date"])
    prepared["symbol"] = prepared["symbol"].astype(str)
    prepared = prepared.sort_values(["symbol", "date"]).reset_index(drop=True)
    return prepared


def _is_limit_up(frame: pd.DataFrame) -> pd.Series:
    return frame["close"].astype(float) >= frame["limit_up_price"].astype(float)


def _is_limit_down(frame: pd.DataFrame) -> pd.Series:
    return frame["close"].astype(float) <= frame["limit_down_price"].astype(float)


def _prior_state(frame: pd.DataFrame, state: str, derived_flag: pd.Series) -> pd.Series:
    if "prior_limit_state" in frame.columns:
        return frame["prior_limit_state"].fillna("none").astype(str).eq(state)
    return (
        derived_flag.groupby(frame["symbol"], group_keys=False)
        .shift(1)
        .fillna(False)
        .astype(bool)
    )


def _rank_pct_by_date(values: pd.Series, dates: pd.Series, mask: pd.Series) -> pd.Series:
    masked = values.astype(float).where(mask)
    return masked.groupby(dates).rank(method="average", pct=True)


def _limit_lock_strength(frame: pd.DataFrame) -> pd.Series:
    is_limit_up = _is_limit_up(frame)
    consecutive = _consecutive_true_by_symbol(frame, is_limit_up)
    shifted_avg_volume = (
        frame["volume"].astype(float)
        .groupby(frame["symbol"], group_keys=False)
        .transform(lambda series: series.shift(1).rolling(5, min_periods=1).mean())
    )
    ratio = frame["volume"].astype(float) / shifted_avg_volume
    values = is_limit_up.astype(float) * consecutive.astype(float) * ratio.clip(upper=1.0)
    return values.where(is_limit_up, 0.0)


def _limit_lock_persistence(frame: pd.DataFrame) -> pd.Series:
    flag = _is_limit_up(frame).astype(float)
    return (
        flag.groupby(frame["symbol"], group_keys=False)
        .transform(lambda series: series.rolling(3, min_periods=1).sum())
        / 3.0
    )


def _failed_limit_breakout_reversal(frame: pd.DataFrame) -> pd.Series:
    event = frame["high"].astype(float) >= frame["limit_up_price"].astype(float)
    event &= frame["close"].astype(float) < frame["limit_up_price"].astype(float)
    close_distance = frame["close"].astype(float) / frame["limit_up_price"].astype(float) - 1.0
    volume_ratio = frame["volume"].astype(float) / frame["avg_volume_20"].astype(float)
    values = -_rank_pct_by_date(close_distance, frame["date"], event) * _rank_pct_by_date(
        volume_ratio,
        frame["date"],
        event,
    )
    return values.where(event, 0.0)


def _post_limit_opening_pressure(frame: pd.DataFrame) -> pd.Series:
    prior_limit_up = _prior_state(frame, "limit_up", _is_limit_up(frame))
    open_gap = frame["open"].astype(float) / frame["prev_close"].astype(float) - 1.0
    turnover = frame["turnover"].astype(float)
    values = _rank_pct_by_date(open_gap, frame["date"], prior_limit_up) * _rank_pct_by_date(
        turnover,
        frame["date"],
        prior_limit_up,
    )
    return values.where(prior_limit_up, 0.0)


def _one_word_board_exclusion(frame: pd.DataFrame, volume_ratio_threshold: float) -> pd.Series:
    open_ = frame["open"].astype(float)
    high = frame["high"].astype(float)
    low = frame["low"].astype(float)
    close = frame["close"].astype(float)
    limit_up = frame["limit_up_price"].astype(float)
    volume_ratio = frame["volume"].astype(float) / frame["avg_volume_20"].astype(float)
    is_one_word = (
        open_.eq(high)
        & high.eq(low)
        & low.eq(close)
        & close.eq(limit_up)
        & (volume_ratio < volume_ratio_threshold)
    )
    return is_one_word.astype(float)


def _limit_gap_decay(frame: pd.DataFrame) -> pd.Series:
    prior_limit_up = _prior_state(frame, "limit_up", _is_limit_up(frame))
    open_gap = frame["open"].astype(float) / frame["prev_close"].astype(float) - 1.0
    intraday_return = frame["close"].astype(float) / frame["open"].astype(float) - 1.0
    values = _rank_pct_by_date(open_gap, frame["date"], prior_limit_up) - _rank_pct_by_date(
        intraday_return,
        frame["date"],
        prior_limit_up,
    )
    return values.where(prior_limit_up, 0.0)


def _limit_down_liquidity_recovery(frame: pd.DataFrame) -> pd.Series:
    prior_limit_down = _prior_state(frame, "limit_down", _is_limit_down(frame))
    volume_ratio = frame["volume"].astype(float) / frame["avg_volume_20"].astype(float)
    recovery = frame["close"].astype(float) / frame["low"].astype(float) - 1.0
    values = _rank_pct_by_date(volume_ratio, frame["date"], prior_limit_down) * _rank_pct_by_date(
        recovery,
        frame["date"],
        prior_limit_down,
    )
    return values.where(prior_limit_down, 0.0)


def _limit_queue_pressure_proxy(frame: pd.DataFrame, *, level2_available: bool) -> pd.Series:
    if level2_available:
        required = {"queue_size_at_limit", "free_float_shares"}
        missing = sorted(required - set(frame.columns))
        if missing:
            raise FactorInputFrameError(f"Level-2 queue proxy missing required columns: {missing}")
        return frame["queue_size_at_limit"].astype(float) / frame["free_float_shares"].astype(float)

    is_limit_up = _is_limit_up(frame).astype(float)
    volume_ratio = frame["volume"].astype(float) / frame["avg_volume_20"].astype(float)
    return is_limit_up * (1.0 - volume_ratio)


def _consecutive_true_by_symbol(frame: pd.DataFrame, flag: pd.Series) -> pd.Series:
    def consecutive(series: pd.Series) -> pd.Series:
        count = 0
        values: list[int] = []
        for item in series.astype(bool):
            count = count + 1 if item else 0
            values.append(count)
        return pd.Series(values, index=series.index)

    return flag.groupby(frame["symbol"], group_keys=False).apply(consecutive)


def _build_factor_output(
    frame: pd.DataFrame,
    *,
    factor_id: str,
    factor_value: pd.Series,
    as_of: pd.Timestamp | None,
    available_at: pd.Timestamp | None,
) -> pd.DataFrame:
    default_as_of = frame["date"].dt.normalize() + pd.Timedelta(hours=15)
    as_of_values = pd.Timestamp(as_of) if as_of is not None else default_as_of
    available_at_values = pd.Timestamp(available_at) if available_at is not None else as_of_values
    output = pd.DataFrame(
        {
            "date": frame["date"].dt.normalize(),
            "symbol": frame["symbol"],
            "factor_value": factor_value.astype(float),
            "factor_id": factor_id,
            "as_of": as_of_values,
            "available_at": available_at_values,
        }
    )
    return validate_factor_output_frame(output.loc[:, FACTOR_OUTPUT_COLUMNS].reset_index(drop=True))

