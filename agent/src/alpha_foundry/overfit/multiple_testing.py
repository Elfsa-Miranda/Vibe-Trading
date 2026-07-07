"""Multiple-testing and selection-disclosure reports."""

from __future__ import annotations

from collections import Counter

from pydantic import BaseModel, ConfigDict, Field

from src.alpha_foundry.common.errors import HardFailureCode
from src.alpha_foundry.overfit.pbo import default_dsr_placeholder, default_pbo_placeholder
from src.alpha_foundry.overfit.trial_ledger import TrialLedger, TrialRecord


class MultipleTestingReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "2.1.0"
    report_id: str
    family_id: str
    sub_family_id: str | None = None
    trial_count: int | None = None
    family_trial_count: int | None = None
    selected_trial_id: str | None = None
    selected_metric: str | None = None
    selection_policy: str | None = None
    fdr_adjusted_pvalues: dict[str, float] | None = None
    dsr_experimental: bool = True
    pbo_experimental: bool = True
    hard_failures: list[HardFailureCode] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    included_trial_ids: list[str] = Field(default_factory=list)
    outcome_counts: dict[str, int] = Field(default_factory=dict)


def build_multiple_testing_report(
    ledger: TrialLedger | None,
    *,
    family_id: str,
    sub_family_id: str | None = None,
    selected_trial_id: str | None = None,
    selected_metric: str | None = None,
    selection_policy: str | None = None,
    strong_result_claim: bool = False,
    fdr_adjusted_pvalues: dict[str, float] | None = None,
) -> MultipleTestingReport:
    records = _records_for(ledger, family_id=family_id, sub_family_id=sub_family_id)
    trial_count = len(records) if ledger is not None else None
    family_trial_count = (
        sum(1 for record in ledger.records if record.family_id == family_id) if ledger is not None else None
    )
    included_trial_ids = [record.trial_id for record in records]
    outcome_counts = dict(Counter(record.outcome for record in records))
    hard_failures: list[HardFailureCode] = []
    warnings: list[str] = []

    if strong_result_claim and trial_count is None:
        hard_failures.append(HardFailureCode.TRIAL_COUNT_MISSING)

    if selected_trial_id is not None and not trial_count:
        hard_failures.append(HardFailureCode.BEST_TRIAL_ONLY)

    if trial_count is not None and trial_count > 1 and not selection_policy:
        hard_failures.append(HardFailureCode.MULTIPLE_TESTING_NOT_DISCLOSED)

    dsr = default_dsr_placeholder()
    pbo = default_pbo_placeholder()
    if dsr.experimental or pbo.experimental:
        warnings.append("dsr_pbo_experimental_not_pass_gate")

    return MultipleTestingReport(
        report_id=f"multiple-testing-{family_id}-{sub_family_id or 'all'}",
        family_id=family_id,
        sub_family_id=sub_family_id,
        trial_count=trial_count,
        family_trial_count=family_trial_count,
        selected_trial_id=selected_trial_id,
        selected_metric=selected_metric,
        selection_policy=selection_policy,
        fdr_adjusted_pvalues=fdr_adjusted_pvalues,
        dsr_experimental=dsr.experimental,
        pbo_experimental=pbo.experimental,
        hard_failures=_dedupe_failures(hard_failures),
        warnings=sorted(set(warnings)),
        included_trial_ids=included_trial_ids,
        outcome_counts=outcome_counts,
    )


def _records_for(
    ledger: TrialLedger | None,
    *,
    family_id: str,
    sub_family_id: str | None,
) -> list[TrialRecord]:
    if ledger is None:
        return []
    records: list[TrialRecord] = []
    for record in ledger.records:
        if record.family_id != family_id:
            continue
        if sub_family_id is not None and record.sub_family_id != sub_family_id:
            continue
        records.append(record)
    return records


def _dedupe_failures(failures: list[HardFailureCode]) -> list[HardFailureCode]:
    output: list[HardFailureCode] = []
    for failure in failures:
        if failure not in output:
            output.append(failure)
    return output

