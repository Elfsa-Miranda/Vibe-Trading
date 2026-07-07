from __future__ import annotations

import pandas as pd


TRADING_DAYS = pd.to_datetime(
    [
        "2026-01-02",
        "2026-01-05",
        "2026-01-06",
        "2026-01-07",
    ]
)

STANDARD_SCENARIOS = (
    "normal_day",
    "limit_up",
    "limit_down",
    "one_word_board",
    "suspension",
    "ST",
    "new_stock",
    "missing_fields",
    "holiday_spillover",
    "future_data_trap",
)
