from __future__ import annotations

import pandas as pd

from src.alpha_foundry.diagnostics import controls


def _factor_and_returns() -> tuple[pd.DataFrame, pd.DataFrame]:
    factor_rows: list[dict[str, object]] = []
    return_rows: list[dict[str, object]] = []
    for day_idx in range(4):
        day = pd.Timestamp("2026-01-05") + pd.Timedelta(days=day_idx)
        for symbol_idx in range(35):
            symbol = f"S{symbol_idx:03d}"
            factor_rows.append(
                {
                    "date": day,
                    "symbol": symbol,
                    "factor_id": "residual_20d_momentum",
                    "factor_value": float(symbol_idx),
                    "as_of": day + pd.Timedelta(hours=15),
                    "signal_time": "T close",
                    "available_at": day + pd.Timedelta(hours=15),
                    "data_availability_policy": "bar_close_derived",
                    "factor_definition_hash": "factor-hash",
                }
            )
            return_rows.append(
                {
                    "date": day,
                    "symbol": symbol,
                    "close_return": float(symbol_idx) / 100.0,
                }
            )
    return pd.DataFrame(factor_rows), pd.DataFrame(return_rows)


def test_placebo_controls_are_generated_by_deterministic_label_permutation() -> None:
    assert hasattr(controls, "permuted_label_rank_ics")
    factor, returns = _factor_and_returns()

    first = controls.permuted_label_rank_ics(
        factor,
        returns,
        return_column="close_return",
        n_permutations=5,
        random_seed=20260708,
    )
    second = controls.permuted_label_rank_ics(
        factor,
        returns,
        return_column="close_return",
        n_permutations=5,
        random_seed=20260708,
    )

    assert first == second
    assert len(first) == 5
    assert all(abs(value) < 0.8 for value in first)
    assert len(set(first)) > 1
