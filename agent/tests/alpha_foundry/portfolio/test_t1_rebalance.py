from __future__ import annotations

import pandas as pd
import pytest

from src.alpha_foundry.portfolio.rebalance import T1ConstraintViolation, check_t1_rebalance_feasibility


def test_same_day_buy_and_sell_raises_t1_violation() -> None:
    trades = pd.DataFrame(
        {
            "date": [pd.Timestamp("2026-01-05"), pd.Timestamp("2026-01-05")],
            "symbol": ["S001", "S001"],
            "side": ["buy", "sell"],
            "shares": [100, 100],
        }
    )

    with pytest.raises(T1ConstraintViolation):
        check_t1_rebalance_feasibility(trades)


def test_t1_rebalance_separates_buy_and_sell_turnover() -> None:
    trades = pd.DataFrame(
        {
            "date": [pd.Timestamp("2026-01-05"), pd.Timestamp("2026-01-06")],
            "symbol": ["S001", "S001"],
            "side": ["buy", "sell"],
            "notional": [10_000.0, 8_000.0],
            "shares": [1_000, 1_000],
        }
    )

    result = check_t1_rebalance_feasibility(trades)

    assert result.t_plus_one_feasible is True
    assert result.buy_turnover == 10_000.0
    assert result.sell_turnover == 8_000.0

