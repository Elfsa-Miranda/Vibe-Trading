from __future__ import annotations

import pandas as pd
import pytest

from src.alpha_foundry.common.errors import ConclusionLevel
from src.alpha_foundry.diagnostics.neutralization import (
    STANDARD_NEUTRALIZATION_CONFIG,
    neutralize_factor_frame,
)


def _factor_frame(values: list[float]) -> pd.DataFrame:
    symbols = [f"S{i:03d}" for i in range(len(values))]
    return pd.DataFrame(
        {
            "date": pd.Timestamp("2026-01-05"),
            "symbol": symbols,
            "factor_id": "residual_20d_momentum",
            "factor_value": values,
            "as_of": pd.Timestamp("2026-01-05 15:00:00"),
            "signal_time": "T close",
            "available_at": pd.Timestamp("2026-01-05 15:00:00"),
            "data_availability_policy": "bar_close_derived",
            "factor_definition_hash": "hash-residual-20d-momentum",
        }
    )


def _exposures(n: int) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.Timestamp("2026-01-05"),
            "symbol": [f"S{i:03d}" for i in range(n)],
            "industry": ["SW_BANK" if i % 2 == 0 else "SW_TECH" for i in range(n)],
            "float_mktcap": [100.0 + i for i in range(n)],
            "beta_60d": [0.8 + (i % 5) * 0.1 for i in range(n)],
            "log_avg_daily_turnover_20d": [1.0 + (i % 7) * 0.05 for i in range(n)],
        }
    )


def test_standard_neutralization_config_is_fixed() -> None:
    config = STANDARD_NEUTRALIZATION_CONFIG

    assert config.industry_classification == "SW_L1"
    assert config.market_cap == "float_mktcap"
    assert config.beta == "60 trading days vs CSI_500"
    assert config.liquidity_proxy == "log_avg_daily_turnover_20d"
    assert config.regression == "cross_sectional_WLS"
    assert config.outlier_treatment == "winsorize 1%-99%"
    assert config.min_cross_section_size == 30


def test_neutralization_removes_size_exposure() -> None:
    n = 35
    exposure_frame = _exposures(n)
    size_signal = exposure_frame["float_mktcap"].rank(pct=True)
    factor = _factor_frame(list(size_signal * 2.0))

    result = neutralize_factor_frame(factor, exposure_frame)
    assert result.warnings == []
    assert result.frame["factor_value"].abs().max() < 1e-12


def test_small_cross_section_skips_neutralization_and_caps_exploratory() -> None:
    factor = _factor_frame([0.1, 0.2, 0.3])
    result = neutralize_factor_frame(factor, _exposures(3))

    assert "cross_section_size_below_30" in result.warnings
    assert result.conclusion_cap == ConclusionLevel.exploratory
    assert list(result.frame["factor_value"]) == pytest.approx([0.1, 0.2, 0.3])
