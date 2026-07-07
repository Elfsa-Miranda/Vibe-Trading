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
