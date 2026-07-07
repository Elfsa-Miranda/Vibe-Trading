"""FactorOutputFrame protocol validation."""

from __future__ import annotations

import pandas as pd


FACTOR_OUTPUT_COLUMNS = ["date", "symbol", "factor_value", "factor_id", "as_of", "available_at"]
FORBIDDEN_FACTOR_OUTPUT_COLUMNS = {
    "forward_return",
    "execution_return",
    "close_return",
    "label",
    "target",
    "next_close",
    "next_day_tradability_outcome",
}


class FactorOutputFrameError(ValueError):
    """Raised when a frame violates the FactorOutputFrame contract."""


def validate_factor_output_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(frame.index, pd.RangeIndex):
        raise FactorOutputFrameError("FactorOutputFrame requires a RangeIndex")

    columns = list(frame.columns)
    forbidden = [col for col in columns if col in FORBIDDEN_FACTOR_OUTPUT_COLUMNS or col.startswith("future_")]
    if forbidden:
        raise FactorOutputFrameError(f"FactorOutputFrame contains forbidden columns: {forbidden}")

    missing = [col for col in FACTOR_OUTPUT_COLUMNS if col not in columns]
    if missing:
        raise FactorOutputFrameError(f"FactorOutputFrame missing required columns: {missing}")

    extra = [col for col in columns if col not in FACTOR_OUTPUT_COLUMNS]
    if extra:
        raise FactorOutputFrameError(f"FactorOutputFrame contains non-contract columns: {extra}")

    return frame.loc[:, FACTOR_OUTPUT_COLUMNS].copy()

