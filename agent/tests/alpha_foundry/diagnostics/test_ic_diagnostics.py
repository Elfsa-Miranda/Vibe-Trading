from __future__ import annotations

import pandas as pd
import pytest

from src.alpha_foundry.diagnostics.ic import compute_ic_summary, join_factor_forward_returns
from src.alpha_foundry.panels.interfaces import FactorOutputFrameError


def _factor_frame(values: list[float], *, factor_id: str = "test_factor") -> pd.DataFrame:
    symbols = [f"S{i:03d}" for i in range(len(values))]
    return pd.DataFrame(
        {
            "date": pd.Timestamp("2026-01-05"),
            "symbol": symbols,
            "factor_value": values,
            "factor_id": factor_id,
            "as_of": pd.Timestamp("2026-01-05 15:00:00"),
            "available_at": pd.Timestamp("2026-01-05 15:00:00"),
        }
    )


def _forward_frame(values: list[float], *, column: str = "close_return") -> pd.DataFrame:
    symbols = [f"S{i:03d}" for i in range(len(values))]
    return pd.DataFrame({"date": pd.Timestamp("2026-01-05"), "symbol": symbols, column: values})


def test_ic_summary_joins_forward_returns_only_in_diagnostics_stage() -> None:
    factor = _factor_frame([1.0, 2.0, 3.0, 4.0])
    returns = _forward_frame([0.01, 0.02, 0.03, 0.04])

    joined = join_factor_forward_returns(factor, returns, return_column="close_return")
    summary = compute_ic_summary(factor, returns, return_column="close_return")

    assert "close_return" in joined.columns
    assert "close_return" not in factor.columns
    assert summary.ic_raw == pytest.approx(1.0)
    assert summary.rank_ic_raw == pytest.approx(1.0)
    assert summary.observation_count == 4


def test_ic_summary_rejects_polluted_factor_output_frame() -> None:
    factor = _factor_frame([1.0, 2.0, 3.0])
    factor["forward_return"] = [0.1, 0.2, 0.3]

    with pytest.raises(FactorOutputFrameError, match="forbidden"):
        compute_ic_summary(factor, _forward_frame([0.1, 0.2, 0.3]), return_column="close_return")

