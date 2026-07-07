"""FactorSpec and formula contracts."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.alpha_foundry.common.errors import ConclusionLevel
from src.alpha_foundry.common.hashing import canonical_hash


TransformName = Literal["winsorize", "rank", "zscore", "neutralize", "clip", "fill_missing"]
DataAvailabilityPolicy = Literal[
    "bar_close_derived",
    "announcement_time_derived",
    "available_at_required",
    "level2_required",
    "fixture_only",
]
FactorDirection = Literal["long", "short", "long_short", "signed"]


class TransformStep(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    step: TransformName
    params: dict[str, Any] = Field(default_factory=dict)


class FactorFormulaSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    formula_id: str
    formula_version: str
    pseudocode: str
    required_fields: list[str]
    forbidden_fields: list[str] = Field(default_factory=list)
    signal_time: str
    data_availability_policy: DataAvailabilityPolicy
    proxy_note: str | None = None
    formula_hash: str

    @field_validator("required_fields", "forbidden_fields")
    @classmethod
    def _non_empty_items(cls, value: list[str]) -> list[str]:
        if any(not item or not item.strip() for item in value):
            raise ValueError("field names must be non-empty")
        return value


class FactorSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "2.1.0"
    factor_id: str
    hypothesis_id: str
    track: str
    formula: FactorFormulaSpec
    transform_pipeline: list[TransformStep]
    universe_policy: str
    tradability_policy: str
    prediction_horizons: list[int]
    benchmark: str | None = None
    default_direction: FactorDirection
    conclusion_cap: ConclusionLevel = ConclusionLevel.exploratory

    @field_validator("transform_pipeline")
    @classmethod
    def _pipeline_must_be_ordered_list(cls, value: list[TransformStep]) -> list[TransformStep]:
        if not isinstance(value, list):
            raise ValueError("transform_pipeline must be an ordered list")
        return value


class FactorComputeContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    as_of_policy: str
    calendar: str = "SSE_SZSE"
    data_audit_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


def factor_definition_hash(spec: FactorSpec) -> str:
    return canonical_hash(spec)


def _specs_dir() -> Path:
    return Path(__file__).parent / "specs"


def load_factor_specs(name: str) -> list[FactorSpec]:
    path = _specs_dir() / f"{name}_specs.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("factors"), list):
        raise ValueError(f"{path} must contain factors list")
    return [FactorSpec.model_validate(item) for item in raw["factors"]]

