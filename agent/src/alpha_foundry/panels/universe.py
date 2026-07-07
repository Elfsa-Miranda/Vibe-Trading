"""Universe contract placeholders for Phase 2."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class UniverseSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "2.1.0"
    universe_id: str
    as_of: str
    symbols: list[str]
    pit_safe: bool = False
    warnings: list[str] = Field(default_factory=list)

