"""Portfolio attribution placeholders for MVP reports."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class PortfolioAttribution(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "2.1.0"
    alpha_return: float | None = None
    risk_return: float | None = None
    cost_bps: float | None = None
    is_production_attribution: bool = False

