"""Alpha hypothesis schema."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


Track = Literal[
    "limit_liquidity_microstructure",
    "residual_price_volume_behavior",
    "pit_financial_quality_revision",
]

Direction = Literal["long", "short", "long_short", "signed", "unknown"]
CrowdingRisk = Literal["high", "medium", "low", "unknown"]

REQUIRED_FALSIFICATION_GATES = {
    "pit",
    "tradability",
    "neutralization",
    "regime",
    "cost",
    "oos",
}


class AlphaHypothesis(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "2.1.0"
    hypothesis_id: str
    name: str
    track: Track
    market_mechanism: str
    economic_rationale: str
    required_data: list[str]
    pit_requirements: list[str]
    tradability_constraints: list[str]
    formation_window: str
    prediction_horizon: str
    expected_decay: str
    direction: Direction
    known_risks: list[str]
    known_public_analogues: list[str] = Field(default_factory=list)
    crowding_risk: CrowdingRisk
    falsification_tests_required: list[str]
    invalidation_conditions: list[str]
    proxy_note: str | None = None
    exploratory_only: bool = False
    created_by: str = "system"

    @field_validator(
        "hypothesis_id",
        "name",
        "market_mechanism",
        "economic_rationale",
        "formation_window",
        "prediction_horizon",
        "expected_decay",
        "created_by",
    )
    @classmethod
    def _non_empty_string(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must be non-empty")
        return value

    @field_validator(
        "required_data",
        "pit_requirements",
        "tradability_constraints",
        "known_risks",
        "falsification_tests_required",
        "invalidation_conditions",
    )
    @classmethod
    def _non_empty_list(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("must be non-empty")
        if any(not item or not item.strip() for item in value):
            raise ValueError("items must be non-empty")
        return value

    @model_validator(mode="after")
    def _validate_research_contract(self) -> "AlphaHypothesis":
        missing_gates = REQUIRED_FALSIFICATION_GATES - set(self.falsification_tests_required)
        if missing_gates:
            missing = ", ".join(sorted(missing_gates))
            raise ValueError(f"falsification_tests_required missing required gates: {missing}")

        if self.hypothesis_id == "limit_queue_pressure_proxy":
            if not self.exploratory_only:
                raise ValueError("limit_queue_pressure_proxy must be exploratory_only without Level-2 data")
            if not self.proxy_note or "Level-2" not in self.proxy_note:
                raise ValueError("limit_queue_pressure_proxy requires an EOD proxy_note mentioning Level-2")

        if self.track == "pit_financial_quality_revision" and not self.exploratory_only:
            raise ValueError("financial-quality draft hypotheses must remain exploratory_only in Phase 1")

        return self

