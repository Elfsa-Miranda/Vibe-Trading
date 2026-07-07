"""FactorPanelContract schema."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FactorPanelContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "2.1.0"
    panel_id: str
    protocol_hash: str | None = None
    hypothesis_ids: list[str]
    factor_ids: list[str]
    as_of_policy: str
    frequency: str = "1D"
    calendar: str = "SSE_SZSE"
    coverage_by_date: dict[str, float]
    min_cross_section_coverage_warn: float = 0.60
    min_cross_section_coverage_drop: float = 0.30
    universe_ref: str
    data_audit_refs: list[str]
    factor_definition_hashes: dict[str, str]
    implementation_status: Literal["draft", "fixture_only", "tested"] = "draft"
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_tested_contract(self) -> "FactorPanelContract":
        if self.implementation_status == "tested" and not self.protocol_hash:
            raise ValueError("protocol_hash is required when implementation_status is tested")
        return self

    def coverage_warnings(self) -> list[str]:
        warnings: list[str] = []
        for date_key, coverage in sorted(self.coverage_by_date.items()):
            if coverage < self.min_cross_section_coverage_drop:
                warnings.append(f"coverage below drop threshold on {date_key}: {coverage:.4f}")
            elif coverage < self.min_cross_section_coverage_warn:
                warnings.append(f"coverage below warn threshold on {date_key}: {coverage:.4f}")
        return warnings

    def ic_eligible_dates(self) -> list[str]:
        return [
            date_key
            for date_key, coverage in sorted(self.coverage_by_date.items())
            if coverage >= self.min_cross_section_coverage_drop
        ]

