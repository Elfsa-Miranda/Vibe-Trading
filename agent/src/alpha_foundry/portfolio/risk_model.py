"""Risk model schemas and PSD checks for portfolio gates."""

from __future__ import annotations

from datetime import date
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from src.alpha_foundry.common.errors import HardFailureCode


class RiskModelSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "2.1.0"
    industry_classification: Literal["SW_L1", "SW_L2", "CSRC_L1", "custom"] = "SW_L1"
    industry_source: str | None = None
    market_cap_field: Literal["float_mktcap", "total_mktcap"] = "float_mktcap"
    beta_benchmark: Literal["CSI_500", "CSI_300", "ALL_A"] = "CSI_500"
    beta_window_days: int = 60
    liquidity_proxy: Literal["log_avg_daily_turnover_20d", "amihud_illiq_20d", "log_adv_20d"] = (
        "log_avg_daily_turnover_20d"
    )
    regression: Literal["cross_sectional_wls", "cross_sectional_ols"] = "cross_sectional_wls"
    weights: Literal["sqrt_float_mktcap", "log_float_mktcap", "equal"] = "log_float_mktcap"
    outlier_treatment: str = "winsorize_1_99_by_date"
    min_cross_section_size: int = 30
    max_missing_regressor_ratio: float = 0.20


class RiskModelSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "2.1.0"
    model_id: str
    as_of: date
    universe: list[str]
    spec: RiskModelSpec
    factor_names: list[str]
    factor_loadings: dict[str, dict[str, float]]
    factor_covariance: dict[str, dict[str, float]]
    residual_variance: dict[str, float]
    estimation_window_days: int
    model_type: Literal["statistical", "fundamental_proxy", "identity_stub"]
    covariance_psd: bool
    is_stub: bool = False
    warnings: list[str] = Field(default_factory=list)


def covariance_is_psd(matrix: np.ndarray, *, tolerance: float = 1e-10) -> bool:
    symmetric = (matrix + matrix.T) / 2.0
    eigenvalues = np.linalg.eigvalsh(symmetric)
    return bool(np.min(eigenvalues) >= -tolerance)


def repair_covariance_psd(matrix: np.ndarray, *, floor: float = 1e-10) -> np.ndarray:
    symmetric = (matrix + matrix.T) / 2.0
    eigenvalues, eigenvectors = np.linalg.eigh(symmetric)
    clipped = np.maximum(eigenvalues, floor)
    repaired = (eigenvectors * clipped) @ eigenvectors.T
    return (repaired + repaired.T) / 2.0


def build_risk_model_snapshot(
    *,
    model_id: str,
    as_of: date,
    universe: list[str],
    factor_names: list[str],
    factor_covariance_matrix: np.ndarray,
    residual_variance: dict[str, float],
    estimation_window_days: int,
    spec: RiskModelSpec | None = None,
    repair_non_psd: bool = True,
) -> RiskModelSnapshot:
    spec = spec or RiskModelSpec()
    covariance = np.array(factor_covariance_matrix, dtype=float)
    warnings: list[str] = []
    psd = covariance_is_psd(covariance)
    if not psd and repair_non_psd:
        covariance = repair_covariance_psd(covariance)
        warnings.append("covariance_repaired_by_eigenvalue_clipping")
        psd = covariance_is_psd(covariance)

    return RiskModelSnapshot(
        model_id=model_id,
        as_of=as_of,
        universe=universe,
        spec=spec,
        factor_names=factor_names,
        factor_loadings={symbol: {} for symbol in universe},
        factor_covariance=_matrix_to_nested_dict(covariance, factor_names),
        residual_variance=residual_variance,
        estimation_window_days=estimation_window_days,
        model_type="fundamental_proxy",
        covariance_psd=psd,
        is_stub=False,
        warnings=warnings,
    )


def validate_portfolio_candidate_gate(
    risk_model_snapshot: RiskModelSnapshot | None,
    *,
    benchmark_id: str | None,
) -> list[HardFailureCode]:
    failures: list[HardFailureCode] = []
    if benchmark_id is None:
        failures.append(HardFailureCode.BENCHMARK_MISSING)
    if risk_model_snapshot is None:
        failures.append(HardFailureCode.RISK_MODEL_MISSING)
    elif not risk_model_snapshot.covariance_psd:
        failures.append(HardFailureCode.RISK_MODEL_NOT_PSD)
    return failures


def _matrix_to_nested_dict(matrix: np.ndarray, names: list[str]) -> dict[str, dict[str, float]]:
    return {
        row_name: {col_name: float(matrix[i, j]) for j, col_name in enumerate(names)}
        for i, row_name in enumerate(names)
    }

