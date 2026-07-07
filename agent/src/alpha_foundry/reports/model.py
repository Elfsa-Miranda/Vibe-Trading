"""Canonical Alpha Foundry report models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.alpha_foundry.common.errors import ConclusionLevel, HardFailureCode


class FactorCandidateCard(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "2.1.0"
    card_id: str
    factor_id: str
    hypothesis_id: str
    falsification_report_ref: str
    factor_definition_hash: str
    conclusion_level: ConclusionLevel
    key_metrics: dict[str, float | None] = Field(default_factory=dict)
    hard_failures: list[HardFailureCode] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    next_action: Literal["reject", "revise", "portfolio_test", "forward_track"]
    trial_count: int | None = None
    proxy_note: str | None = None
    uses_execution_return: bool = False
    has_close_return_diagnostics: bool = True
    evidence_refs: list[str] = Field(default_factory=list)

    @field_validator("hard_failures")
    @classmethod
    def _dedupe_hard_failures(cls, value: list[HardFailureCode]) -> list[HardFailureCode]:
        return _dedupe_failures(value)

    @field_validator("warnings", "evidence_refs")
    @classmethod
    def _dedupe_strings(cls, value: list[str]) -> list[str]:
        return _dedupe_strings(value)


class AlphaFoundryReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "2.1.0"
    report_id: str
    protocol_hash: str
    hypothesis_refs: list[str] = Field(default_factory=list)
    factor_candidate_cards: list[FactorCandidateCard] = Field(default_factory=list)
    portfolio_report_refs: list[str] = Field(default_factory=list)
    forward_plan_refs: list[str] = Field(default_factory=list)
    trial_ledger_ref: str | None = None
    conclusion_level: ConclusionLevel
    hard_failures: list[HardFailureCode] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    research_card_ref: str | None = None

    @field_validator("hard_failures")
    @classmethod
    def _dedupe_hard_failures(cls, value: list[HardFailureCode]) -> list[HardFailureCode]:
        return _dedupe_failures(value)

    @field_validator("warnings", "hypothesis_refs", "portfolio_report_refs", "forward_plan_refs")
    @classmethod
    def _dedupe_strings(cls, value: list[str]) -> list[str]:
        return _dedupe_strings(value)


def _dedupe_failures(values: list[HardFailureCode]) -> list[HardFailureCode]:
    output: list[HardFailureCode] = []
    for value in values:
        if value not in output:
            output.append(value)
    return output


def _dedupe_strings(values: list[str]) -> list[str]:
    output: list[str] = []
    for value in values:
        if value not in output:
            output.append(value)
    return output
