from __future__ import annotations

import pandas as pd


def make_factor_output_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-01-05", "2026-01-05"]),
            "symbol": ["000001.SZ", "000002.SZ"],
            "factor_value": [0.4, -0.2],
            "factor_id": ["limit_lock_strength", "limit_lock_strength"],
            "as_of": pd.to_datetime(["2026-01-05 15:00:00", "2026-01-05 15:00:00"]),
            "available_at": pd.to_datetime(["2026-01-05 15:00:00", "2026-01-05 15:00:00"]),
        }
    )


def make_forward_return_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-01-05"]),
            "symbol": ["000001.SZ"],
            "close_return": [0.02],
            "execution_return": [0.015],
        }
    )


def make_tradability_input_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": "OK001",
                "open": 10.0,
                "high": 10.5,
                "low": 9.8,
                "close": 10.2,
                "limit_up_price": 11.0,
                "limit_down_price": 9.0,
                "volume": 100000,
                "avg_volume_20": 90000,
                "is_suspended": False,
                "st_announcement_date": pd.NaT,
                "st_announcement_after_close": False,
                "listing_date": pd.Timestamp("2025-01-01"),
            },
            {
                "symbol": "LUP001",
                "open": 11.0,
                "high": 11.0,
                "low": 10.5,
                "close": 11.0,
                "limit_up_price": 11.0,
                "limit_down_price": 9.0,
                "volume": 100000,
                "avg_volume_20": 90000,
                "is_suspended": False,
                "st_announcement_date": pd.NaT,
                "st_announcement_after_close": False,
                "listing_date": pd.Timestamp("2025-01-01"),
            },
            {
                "symbol": "SUS001",
                "open": 10.0,
                "high": 10.0,
                "low": 10.0,
                "close": 10.0,
                "limit_up_price": 11.0,
                "limit_down_price": 9.0,
                "volume": 0,
                "avg_volume_20": 90000,
                "is_suspended": True,
                "st_announcement_date": pd.NaT,
                "st_announcement_after_close": False,
                "listing_date": pd.Timestamp("2025-01-01"),
            },
            {
                "symbol": "ST001",
                "open": 10.0,
                "high": 10.3,
                "low": 9.9,
                "close": 10.1,
                "limit_up_price": 11.0,
                "limit_down_price": 9.0,
                "volume": 100000,
                "avg_volume_20": 90000,
                "is_suspended": False,
                "st_announcement_date": pd.Timestamp("2026-01-05"),
                "st_announcement_after_close": True,
                "listing_date": pd.Timestamp("2025-01-01"),
            },
            {
                "symbol": "NEW001",
                "open": 10.0,
                "high": 10.3,
                "low": 9.9,
                "close": 10.1,
                "limit_up_price": 11.0,
                "limit_down_price": 9.0,
                "volume": 100000,
                "avg_volume_20": 90000,
                "is_suspended": False,
                "st_announcement_date": pd.NaT,
                "st_announcement_after_close": False,
                "listing_date": pd.Timestamp("2025-12-30"),
            },
            {
                "symbol": "OWB001",
                "open": 11.0,
                "high": 11.0,
                "low": 11.0,
                "close": 11.0,
                "limit_up_price": 11.0,
                "limit_down_price": 9.0,
                "volume": 1000,
                "avg_volume_20": 100000,
                "is_suspended": False,
                "st_announcement_date": pd.NaT,
                "st_announcement_after_close": False,
                "listing_date": pd.Timestamp("2025-01-01"),
            },
        ]
    )


def make_limit_liquidity_factor_input_frame() -> pd.DataFrame:
    """Two-date fixture with deterministic limit/liquidity mechanism scenarios."""

    previous = pd.Timestamp("2026-01-02")
    current = pd.Timestamp("2026-01-05")

    def row(
        *,
        day: pd.Timestamp,
        symbol: str,
        open_: float,
        high: float,
        low: float,
        close: float,
        prev_close: float,
        limit_up_price: float,
        limit_down_price: float,
        volume: float,
        avg_volume_20: float,
        turnover: float,
        prior_limit_state: str = "none",
    ) -> dict[str, object]:
        return {
            "date": day,
            "symbol": symbol,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "prev_close": prev_close,
            "limit_up_price": limit_up_price,
            "limit_down_price": limit_down_price,
            "volume": volume,
            "avg_volume_20": avg_volume_20,
            "turnover": turnover,
            "prior_limit_state": prior_limit_state,
            "is_suspended": False,
            "st_announcement_date": pd.NaT,
            "st_announcement_after_close": False,
            "listing_date": pd.Timestamp("2025-01-01"),
        }

    rows: list[dict[str, object]] = []

    # Lock strength and persistence.
    rows.extend(
        [
            row(
                day=previous,
                symbol="LOCK",
                open_=10.0,
                high=10.0,
                low=9.8,
                close=10.0,
                prev_close=9.1,
                limit_up_price=10.0,
                limit_down_price=8.2,
                volume=100.0,
                avg_volume_20=100.0,
                turnover=0.10,
            ),
            row(
                day=current,
                symbol="LOCK",
                open_=10.8,
                high=11.0,
                low=10.7,
                close=11.0,
                prev_close=10.0,
                limit_up_price=11.0,
                limit_down_price=9.0,
                volume=80.0,
                avg_volume_20=100.0,
                turnover=0.12,
                prior_limit_state="limit_up",
            ),
            row(
                day=previous,
                symbol="FRESH",
                open_=9.7,
                high=9.8,
                low=9.3,
                close=9.5,
                prev_close=9.4,
                limit_up_price=10.0,
                limit_down_price=8.1,
                volume=100.0,
                avg_volume_20=100.0,
                turnover=0.08,
            ),
            row(
                day=current,
                symbol="FRESH",
                open_=10.8,
                high=11.0,
                low=10.7,
                close=11.0,
                prev_close=10.0,
                limit_up_price=11.0,
                limit_down_price=9.0,
                volume=50.0,
                avg_volume_20=100.0,
                turnover=0.11,
            ),
        ]
    )

    # Failed limit breakout.
    rows.extend(
        [
            row(
                day=previous,
                symbol="BREAK",
                open_=10.0,
                high=10.1,
                low=9.8,
                close=10.0,
                prev_close=9.9,
                limit_up_price=11.0,
                limit_down_price=9.0,
                volume=100.0,
                avg_volume_20=100.0,
                turnover=0.10,
            ),
            row(
                day=current,
                symbol="BREAK",
                open_=10.7,
                high=11.0,
                low=10.2,
                close=10.5,
                prev_close=10.0,
                limit_up_price=11.0,
                limit_down_price=9.0,
                volume=200.0,
                avg_volume_20=100.0,
                turnover=0.20,
            ),
        ]
    )

    # Prior limit-up opening pressure.
    for symbol, open_, turnover in [("PRESS_A", 10.5, 0.20), ("PRESS_B", 10.2, 0.10)]:
        rows.append(
            row(
                day=previous,
                symbol=symbol,
                open_=10.0,
                high=10.0,
                low=9.8,
                close=10.0,
                prev_close=9.1,
                limit_up_price=10.0,
                limit_down_price=8.2,
                volume=100.0,
                avg_volume_20=100.0,
                turnover=0.10,
            )
        )
        rows.append(
            row(
                day=current,
                symbol=symbol,
                open_=open_,
                high=10.8,
                low=10.0,
                close=10.4,
                prev_close=10.0,
                limit_up_price=11.0,
                limit_down_price=9.0,
                volume=100.0,
                avg_volume_20=100.0,
                turnover=turnover,
                prior_limit_state="limit_up",
            )
        )

    # One-word board and normal tradable state.
    rows.extend(
        [
            row(
                day=current,
                symbol="OWB",
                open_=11.0,
                high=11.0,
                low=11.0,
                close=11.0,
                prev_close=10.0,
                limit_up_price=11.0,
                limit_down_price=9.0,
                volume=1_000.0,
                avg_volume_20=100_000.0,
                turnover=0.01,
            ),
            row(
                day=current,
                symbol="NORMAL",
                open_=10.1,
                high=10.5,
                low=9.9,
                close=10.2,
                prev_close=10.0,
                limit_up_price=11.0,
                limit_down_price=9.0,
                volume=100_000.0,
                avg_volume_20=100_000.0,
                turnover=0.10,
            ),
        ]
    )

    # Gap decay after prior limit-up.
    for symbol, open_, close in [("GAP_A", 10.5, 10.4), ("GAP_B", 10.2, 10.5)]:
        rows.append(
            row(
                day=previous,
                symbol=symbol,
                open_=10.0,
                high=10.0,
                low=9.8,
                close=10.0,
                prev_close=9.1,
                limit_up_price=10.0,
                limit_down_price=8.2,
                volume=100.0,
                avg_volume_20=100.0,
                turnover=0.10,
            )
        )
        rows.append(
            row(
                day=current,
                symbol=symbol,
                open_=open_,
                high=10.8,
                low=10.0,
                close=close,
                prev_close=10.0,
                limit_up_price=11.0,
                limit_down_price=9.0,
                volume=100.0,
                avg_volume_20=100.0,
                turnover=0.10,
                prior_limit_state="limit_up",
            )
        )

    # Liquidity recovery after prior limit-down.
    for symbol, volume, close in [("DOWN_A", 200.0, 8.8), ("DOWN_B", 100.0, 8.1)]:
        rows.append(
            row(
                day=previous,
                symbol=symbol,
                open_=8.2,
                high=8.3,
                low=8.0,
                close=8.0,
                prev_close=8.8,
                limit_up_price=9.6,
                limit_down_price=8.0,
                volume=100.0,
                avg_volume_20=100.0,
                turnover=0.10,
            )
        )
        rows.append(
            row(
                day=current,
                symbol=symbol,
                open_=8.1,
                high=8.9,
                low=8.0,
                close=close,
                prev_close=8.0,
                limit_up_price=8.8,
                limit_down_price=7.2,
                volume=volume,
                avg_volume_20=100.0,
                turnover=0.10,
                prior_limit_state="limit_down",
            )
        )

    # EOD queue pressure proxy.
    rows.append(
        row(
            day=current,
            symbol="QUEUE",
            open_=10.9,
            high=11.0,
            low=10.8,
            close=11.0,
            prev_close=10.0,
            limit_up_price=11.0,
            limit_down_price=9.0,
            volume=20.0,
            avg_volume_20=100.0,
            turnover=0.02,
        )
    )

    return pd.DataFrame(rows)


def make_price_volume_factor_input_frame() -> pd.DataFrame:
    """Single-date fixture with deterministic residual price/volume scenarios."""

    current = pd.Timestamp("2026-01-05")

    def row(
        *,
        symbol: str,
        close: float = 10.0,
        high: float = 10.5,
        low: float = 9.5,
        volume: float = 100.0,
        turnover: float = 1.0,
        amount: float = 1_000_000.0,
        ret_20d: float = 0.0,
        industry: str = "bank",
        float_mktcap: float = 100.0,
        beta_60d: float = 1.0,
        benchmark_returns: float = 0.0,
        log_avg_daily_turnover_20d: float = 2.0,
        ret_5d: float = 0.0,
        turnover_5d_z: float = 0.0,
        amihud_20d_z: float = 0.0,
        prev_amihud_20d_z: float = 0.0,
        avg_turnover_20d: float = 1.0,
        ret_1d: float = 0.0,
        ret_5d_z: float = 0.0,
        volume_5d_z: float = 0.0,
        breakout_ret_3d: float = 0.0,
        realized_vol_20d_z: float = 0.0,
        turnover_confirm: float = 0.0,
    ) -> dict[str, object]:
        return {
            "date": current,
            "symbol": symbol,
            "close": close,
            "high": high,
            "low": low,
            "volume": volume,
            "turnover": turnover,
            "amount": amount,
            "ret_20d": ret_20d,
            "industry": industry,
            "float_mktcap": float_mktcap,
            "beta_60d": beta_60d,
            "benchmark_returns": benchmark_returns,
            "log_avg_daily_turnover_20d": log_avg_daily_turnover_20d,
            "ret_5d": ret_5d,
            "turnover_5d_z": turnover_5d_z,
            "amihud_20d_z": amihud_20d_z,
            "prev_amihud_20d_z": prev_amihud_20d_z,
            "avg_turnover_20d": avg_turnover_20d,
            "ret_1d": ret_1d,
            "ret_5d_z": ret_5d_z,
            "volume_5d_z": volume_5d_z,
            "breakout_ret_3d": breakout_ret_3d,
            "realized_vol_20d_z": realized_vol_20d_z,
            "turnover_confirm": turnover_confirm,
        }

    return pd.DataFrame(
        [
            row(symbol="RES_A", ret_20d=0.10),
            row(symbol="RES_B", ret_20d=0.04),
            row(symbol="RES_C", ret_20d=-0.02),
            row(symbol="LIQ_A", ret_5d=0.04, turnover_5d_z=1.5, amihud_20d_z=-0.5, prev_amihud_20d_z=0.2),
            row(symbol="LIQ_B", ret_5d=-0.03, turnover_5d_z=1.2, amihud_20d_z=-0.2, prev_amihud_20d_z=0.1),
            row(symbol="LIQ_C", ret_5d=0.05, turnover_5d_z=0.4, amihud_20d_z=0.2, prev_amihud_20d_z=0.1),
            row(symbol="ABN_A", turnover=4.0, avg_turnover_20d=2.0, ret_1d=0.03),
            row(symbol="ABN_B", turnover=1.0, avg_turnover_20d=1.0, ret_1d=-0.01),
            row(symbol="DIV_A", ret_5d=0.05, ret_5d_z=0.5, volume_5d_z=2.0),
            row(symbol="DIV_B", ret_5d=-0.04, ret_5d_z=-0.8, volume_5d_z=1.0),
            row(
                symbol="VOL_A",
                breakout_ret_3d=0.04,
                realized_vol_20d_z=-1.5,
                turnover_confirm=0.2,
            ),
            row(
                symbol="VOL_B",
                breakout_ret_3d=0.01,
                realized_vol_20d_z=-1.5,
                turnover_confirm=-0.1,
            ),
        ]
    )
