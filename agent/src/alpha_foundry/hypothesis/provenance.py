"""Hypothesis provenance models."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class HypothesisProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "2.1.0"
    hypothesis_id: str
    source: Literal["system_default", "manual_review", "research_protocol", "fixture"]
    rationale_ref: str | None = None
    created_at: datetime = Field(default_factory=_utc_now)

