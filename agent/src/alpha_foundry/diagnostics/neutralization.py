"""Standard A-share neutralization helpers."""

from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from src.alpha_foundry.common.errors import ConclusionLevel
from src.alpha_foundry.panels.interfaces import FACTOR_OUTPUT_COLUMNS, validate_factor_output_frame


class StandardNeutralizationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "2.1.0"
    industry_classification: Literal["SW_L1"] = "SW_L1"
    market_cap: Literal["float_mktcap"] = "float_mktcap"
    beta: Literal["60 trading days vs CSI_500"] = "60 trading days vs CSI_500"
    liquidity_proxy: Literal["log_avg_daily_turnover_20d"] = "log_avg_daily_turnover_20d"
    regression: Literal["cross_sectional_WLS"] = "cross_sectional_WLS"
    outlier_treatment: Literal["winsorize 1%-99%"] = "winsorize 1%-99%"
    min_cross_section_size: int = 30
    max_missing_regressor_ratio: float = 0.20


class NeutralizationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)

    schema_version: str = "2.1.0"
    frame: pd.DataFrame
    warnings: list[str] = Field(default_factory=list)
    conclusion_cap: ConclusionLevel = ConclusionLevel.research_candidate
    config: StandardNeutralizationConfig = Field(default_factory=StandardNeutralizationConfig)


STANDARD_NEUTRALIZATION_CONFIG = StandardNeutralizationConfig()


def neutralize_factor_frame(
    factor_frame: pd.DataFrame,
    exposures: pd.DataFrame,
    *,
    config: StandardNeutralizationConfig = STANDARD_NEUTRALIZATION_CONFIG,
) -> NeutralizationResult:
    factor = validate_factor_output_frame(factor_frame)
    required = {"date", "symbol", "industry", "float_mktcap", "beta_60d", "log_avg_daily_turnover_20d"}
    missing = sorted(required - set(exposures.columns))
    if missing:
        raise ValueError(f"exposure frame missing required columns: {missing}")

    exposure_frame = exposures.copy()
    exposure_frame["date"] = pd.to_datetime(exposure_frame["date"]).dt.normalize()
    factor = factor.copy()
    factor["date"] = pd.to_datetime(factor["date"]).dt.normalize()
    joined = factor.merge(exposure_frame, on=["date", "symbol"], how="left")

    residual_parts: list[pd.DataFrame] = []
    warnings: list[str] = []
    for _, group in joined.groupby("date", sort=True):
        if len(group) < config.min_cross_section_size:
            warnings.append("cross_section_size_below_30")
            residual_parts.append(group.loc[:, FACTOR_OUTPUT_COLUMNS])
            continue

        try:
            residual_values, group_warnings = _neutralize_group(group, config)
        except np.linalg.LinAlgError:
            residual_values = group["factor_value"].astype(float).to_numpy()
            group_warnings = ["neutralization_linalg_failed"]
        warnings.extend(group_warnings)
        output_group = group.loc[:, FACTOR_OUTPUT_COLUMNS].copy()
        residual_values[np.abs(residual_values) < 1e-10] = 0.0
        output_group["factor_value"] = residual_values
        residual_parts.append(output_group)

    result = pd.concat(residual_parts, ignore_index=True) if residual_parts else factor
    cap = ConclusionLevel.exploratory if warnings else ConclusionLevel.research_candidate
    return NeutralizationResult(
        frame=validate_factor_output_frame(result.loc[:, FACTOR_OUTPUT_COLUMNS].reset_index(drop=True)),
        warnings=sorted(set(warnings)),
        conclusion_cap=cap,
        config=config,
    )


def _neutralize_group(
    group: pd.DataFrame,
    config: StandardNeutralizationConfig,
) -> tuple[np.ndarray, list[str]]:
    warnings: list[str] = []
    y = group["factor_value"].astype(float).to_numpy()
    pieces: list[np.ndarray] = [np.ones((len(group), 1), dtype=float)]

    industry = pd.get_dummies(group["industry"].astype(str), drop_first=True, dtype=float)
    if not industry.empty:
        single_stock_industries = group["industry"].value_counts()
        if (single_stock_industries == 1).any():
            warnings.append("industry_dummy_single_stock_dropped")
        pieces.append(industry.to_numpy(dtype=float))

    numeric = {
        "float_mktcap": group["float_mktcap"].astype(float),
        "beta_60d": group["beta_60d"].astype(float),
        "log_avg_daily_turnover_20d": group["log_avg_daily_turnover_20d"].astype(float),
    }
    for name, series in numeric.items():
        missing_ratio = float(series.isna().mean())
        if name in {"beta_60d", "log_avg_daily_turnover_20d"} and missing_ratio > config.max_missing_regressor_ratio:
            warnings.append(f"{name}_missing_ratio_gt_20pct")
            continue
        clean = series.fillna(series.median())
        if clean.nunique(dropna=False) > 1:
            pieces.append(clean.to_numpy(dtype=float).reshape(-1, 1))

    design = np.hstack(pieces)
    weights = np.sqrt(np.maximum(np.log(group["float_mktcap"].astype(float).fillna(1.0)), 1.0)).to_numpy(dtype=float)
    beta, *_ = np.linalg.lstsq(design * weights[:, None], y * weights, rcond=None)
    fitted = design @ beta
    return y - fitted, warnings


def _winsorize(values: np.ndarray) -> np.ndarray:
    lower = np.nanquantile(values, 0.01)
    upper = np.nanquantile(values, 0.99)
    return np.clip(values, lower, upper)
