"""Experimental PBO/DSR placeholders for selection disclosure."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ExperimentalSelectionStatistic(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "2.1.0"
    name: str
    experimental: bool = True
    may_be_sole_pass_gate: bool = False
    value: float | None = None


def default_dsr_placeholder() -> ExperimentalSelectionStatistic:
    return ExperimentalSelectionStatistic(name="deflated_sharpe_ratio")


def default_pbo_placeholder() -> ExperimentalSelectionStatistic:
    return ExperimentalSelectionStatistic(name="probability_of_backtest_overfit")

