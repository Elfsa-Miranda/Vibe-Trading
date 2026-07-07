"""Forward return contracts."""

from __future__ import annotations

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field


class ForwardReturnContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "2.1.0"
    horizon_days: int
    close_return_column: str = "close_return"
    execution_return_column: str = "execution_return"
    uses_execution_return: bool
    execution_price_policy: str
    t_plus_one_policy: str
    limit_state_policy: str
    suspension_policy: str
    calendar: str = "SSE_SZSE"
    warnings: list[str] = Field(default_factory=list)


def validate_forward_return_frame(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"date", "symbol", "close_return", "execution_return"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"forward return frame missing columns: {missing}")
    return frame.copy()


def require_execution_return_for_track(track: str, contract: ForwardReturnContract) -> None:
    if track == "limit_liquidity_microstructure" and not contract.uses_execution_return:
        raise ValueError("limit_liquidity_microstructure validation requires execution_return")

