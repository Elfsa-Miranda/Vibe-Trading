"""TrialLedger-derived family matrix."""

from __future__ import annotations

from collections import Counter

from pydantic import BaseModel, ConfigDict, Field

from src.alpha_foundry.overfit.trial_ledger import TrialLedger


class TrialFamilyMatrix(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "2.1.0"
    family_id: str
    family_trial_count: int
    sub_family_counts: dict[str, int] = Field(default_factory=dict)
    outcome_counts: dict[str, int] = Field(default_factory=dict)
    trial_ids: list[str] = Field(default_factory=list)


def build_trial_family_matrix(ledger: TrialLedger) -> TrialFamilyMatrix:
    sub_family_counter: Counter[str] = Counter()
    outcome_counter: Counter[str] = Counter()
    trial_ids: list[str] = []
    for record in ledger.records:
        sub_family_counter[record.sub_family_id or "unknown"] += 1
        outcome_counter[record.outcome] += 1
        trial_ids.append(record.trial_id)
    return TrialFamilyMatrix(
        family_id=ledger.family_id,
        family_trial_count=len(ledger.records),
        sub_family_counts=dict(sub_family_counter),
        outcome_counts=dict(outcome_counter),
        trial_ids=trial_ids,
    )

