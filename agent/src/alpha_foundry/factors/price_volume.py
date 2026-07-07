"""Residual price/volume behavior factors for A-share alpha foundry."""

from __future__ import annotations

from typing import Iterable, Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from src.alpha_foundry.common.errors import ConclusionLevel
from src.alpha_foundry.factors.base import FactorSpec, factor_definition_hash, load_factor_specs
from src.alpha_foundry.panels.interfaces import FACTOR_OUTPUT_COLUMNS, validate_factor_output_frame


PRICE_VOLUME_SPECS = tuple(load_factor_specs("price_volume"))
PRICE_VOLUME_SPEC_BY_ID = {spec.factor_id: spec for spec in PRICE_VOLUME_SPECS}
PRICE_VOLUME_FACTOR_IDS = tuple(spec.factor_id for spec in PRICE_VOLUME_SPECS)

DEFAULT_RESIDUAL_BASIS = {
    "industry_classification": "SW_L1",
    "market_cap": "float_mktcap",
    "beta": "60 trading days vs CSI_500",
    "liquidity_proxy": "log_avg_daily_turnover_20d",
    "regression": "cross_sectional_WLS",
    "outlier_treatment": "winsorize 1%-99%",
    "min_cross_section_size": 30,
}


class PriceVolumeInputFrameError(ValueError):
    """Raised when price/volume factor inputs violate formula contracts."""


class PriceVolumeFactorMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "2.1.0"
    factor_id: str
    default_direction: Literal["long", "short", "long_short", "signed"]
    conclusion_cap: ConclusionLevel
    residual_basis: dict[str, str | int] = Field(default_factory=dict)
    claims_neutralized_ic: bool = False
    claims_alpha_validity: bool = False
    signal_time: str
    data_availability_policy: str
    factor_definition_hash: str
    proxy_note: str | None = None


def get_price_volume_specs() -> dict[str, FactorSpec]:
    return dict(PRICE_VOLUME_SPEC_BY_ID)


def get_price_volume_factor_metadata(factor_id: str) -> PriceVolumeFactorMetadata:
    spec = _get_spec(factor_id)
    return PriceVolumeFactorMetadata(
        factor_id=factor_id,
        default_direction=spec.default_direction,
        conclusion_cap=spec.conclusion_cap,
        residual_basis=dict(DEFAULT_RESIDUAL_BASIS) if factor_id == "residual_20d_momentum" else {},
        signal_time=spec.formula.signal_time,
        data_availability_policy=spec.formula.data_availability_policy,
        factor_definition_hash=factor_definition_hash(spec),
        proxy_note=spec.formula.proxy_note,
    )


def compute_price_volume_factors(
    frame: pd.DataFrame,
    *,
    factor_ids: Iterable[str] | None = None,
) -> dict[str, pd.DataFrame]:
    ids = tuple(factor_ids) if factor_ids is not None else PRICE_VOLUME_FACTOR_IDS
    return {factor_id: compute_price_volume_factor(frame, factor_id) for factor_id in ids}


def compute_price_volume_factor(
    frame: pd.DataFrame,
    factor_id: str,
    *,
    as_of: pd.Timestamp | None = None,
    available_at: pd.Timestamp | None = None,
) -> pd.DataFrame:
    spec = _get_spec(factor_id)
    prepared = _prepare_input_frame(frame, spec)

    if factor_id == "residual_20d_momentum":
        values = _residual_20d_momentum(prepared)
    elif factor_id == "liquidity_conditioned_reversal":
        values = _liquidity_conditioned_reversal(prepared)
    elif factor_id == "abnormal_turnover_unwind":
        values = _abnormal_turnover_unwind(prepared)
    elif factor_id == "volume_price_divergence_reversal":
        values = _volume_price_divergence_reversal(prepared)
    elif factor_id == "volatility_compression_breakout_quality":
        values = _volatility_compression_breakout_quality(prepared)
    else:
        raise PriceVolumeInputFrameError(f"unsupported factor_id: {factor_id}")

    return _build_factor_output(
        prepared,
        factor_id=factor_id,
        factor_value=values,
        as_of=as_of,
        available_at=available_at,
    )


def _get_spec(factor_id: str) -> FactorSpec:
    try:
        return PRICE_VOLUME_SPEC_BY_ID[factor_id]
    except KeyError as exc:
        raise PriceVolumeInputFrameError(f"unknown factor_id: {factor_id}") from exc


def _prepare_input_frame(frame: pd.DataFrame, spec: FactorSpec) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame):
        raise PriceVolumeInputFrameError("factor input must be a pandas DataFrame")

    forbidden = [
        col
        for col in frame.columns
        if col in spec.formula.forbidden_fields or col.startswith("future_")
    ]
    if forbidden:
        raise PriceVolumeInputFrameError(f"factor input contains forbidden columns: {forbidden}")

    required = {"date", "symbol", *spec.formula.required_fields}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise PriceVolumeInputFrameError(f"factor input missing required columns: {missing}")

    prepared = frame.copy()
    prepared["date"] = pd.to_datetime(prepared["date"])
    prepared["symbol"] = prepared["symbol"].astype(str)
    prepared = prepared.sort_values(["date", "symbol"]).reset_index(drop=True)
    return prepared


def _rank_pct_by_date(values: pd.Series, dates: pd.Series, mask: pd.Series | None = None) -> pd.Series:
    rank_input = values.astype(float)
    if mask is not None:
        rank_input = rank_input.where(mask)
    return rank_input.groupby(dates).rank(method="average", pct=True)


def _residual_20d_momentum(frame: pd.DataFrame) -> pd.Series:
    residual = pd.Series(np.nan, index=frame.index, dtype=float)
    for _, group in frame.groupby("date", sort=False):
        y = group["ret_20d"].astype(float)
        design = _residual_design_matrix(group)
        weights = np.sqrt(np.maximum(np.log(group["float_mktcap"].astype(float)), 1.0)).to_numpy(dtype=float)
        x_weighted = design * weights[:, None]
        y_weighted = y.to_numpy(dtype=float) * weights
        beta, *_ = np.linalg.lstsq(x_weighted, y_weighted, rcond=None)
        fitted = design @ beta
        residual.loc[group.index] = y.to_numpy(dtype=float) - fitted
    return residual


def _residual_design_matrix(group: pd.DataFrame) -> np.ndarray:
    pieces: list[np.ndarray] = [np.ones((len(group), 1), dtype=float)]
    industry = pd.get_dummies(group["industry"].astype(str), drop_first=True, dtype=float)
    if not industry.empty:
        pieces.append(industry.to_numpy(dtype=float))

    numeric = pd.DataFrame(
        {
            "log_float_mktcap": np.log(group["float_mktcap"].astype(float)),
            "beta_60d": group["beta_60d"].astype(float),
            "log_avg_daily_turnover_20d": group["log_avg_daily_turnover_20d"].astype(float),
        },
        index=group.index,
    )
    for column in numeric:
        series = numeric[column]
        if series.nunique(dropna=False) > 1:
            pieces.append(series.to_numpy(dtype=float).reshape(-1, 1))

    return np.hstack(pieces)


def _liquidity_conditioned_reversal(frame: pd.DataFrame) -> pd.Series:
    liquidity_shock = frame["turnover_5d_z"].astype(float) > 1.0
    liquidity_improving = frame["amihud_20d_z"].astype(float) < frame["prev_amihud_20d_z"].astype(float)
    condition = liquidity_shock & liquidity_improving
    return (-frame["ret_5d"].astype(float)).where(condition, 0.0)


def _abnormal_turnover_unwind(frame: pd.DataFrame) -> pd.Series:
    turnover_ratio = frame["turnover"].astype(float) / frame["avg_turnover_20d"].astype(float)
    abs_ret = frame["ret_1d"].astype(float).abs()
    return -_rank_pct_by_date(turnover_ratio, frame["date"]) * _rank_pct_by_date(abs_ret, frame["date"])


def _volume_price_divergence_reversal(frame: pd.DataFrame) -> pd.Series:
    divergence = frame["volume_5d_z"].astype(float) - frame["ret_5d_z"].astype(float).abs()
    direction = np.sign(frame["ret_5d"].astype(float))
    return -direction * _rank_pct_by_date(divergence, frame["date"])


def _volatility_compression_breakout_quality(frame: pd.DataFrame) -> pd.Series:
    condition = (frame["realized_vol_20d_z"].astype(float) < -1.0) & (
        frame["turnover_confirm"].astype(float) > 0.0
    )
    breakout_rank = _rank_pct_by_date(frame["breakout_ret_3d"].astype(float), frame["date"])
    return breakout_rank.where(condition, 0.0)


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
