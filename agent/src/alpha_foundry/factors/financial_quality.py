"""PIT availability gate for financial-quality factor adapters."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from src.alpha_foundry.common.errors import ConclusionLevel, HardFailureCode
from src.alpha_foundry.panels.alignment import add_trading_days


DATA_AVAILABILITY_MATRIX_REF = "docs/aaf-v2-data-availability-matrix.md"


class FinancialQualityAvailabilityMode(str, Enum):
    real_available_at = "real_available_at"
    announcement_time_proxy = "announcement_time_proxy"
    adapter_only = "adapter_only"
    invalid = "invalid"


class FinancialQualityAvailabilityReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "2.1.0"
    mode: FinancialQualityAvailabilityMode
    as_of: datetime
    pit_safe: bool
    proxy_assumption: bool
    effective_available_at: datetime | None = None
    conclusion_cap: ConclusionLevel = ConclusionLevel.exploratory
    hard_failures: list[HardFailureCode] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    can_compute_factor_values: bool = False
    can_claim_alpha: bool = False
    data_availability_matrix_ref: str = DATA_AVAILABILITY_MATRIX_REF
    data_audit_refs: list[str] = Field(default_factory=list)


def assess_financial_quality_availability(
    frame: pd.DataFrame,
    *,
    as_of: pd.Timestamp | datetime,
    trading_days: list[pd.Timestamp] | pd.DatetimeIndex,
) -> FinancialQualityAvailabilityReport:
    if frame.empty:
        raise ValueError("financial quality availability assessment requires at least one row")

    row = frame.iloc[0]
    as_of_ts = pd.Timestamp(as_of)
    available_at = _optional_timestamp(row.get("available_at"))
    announcement_time = _optional_timestamp(row.get("announcement_time"))
    report_period_end = _optional_timestamp(row.get("report_period_end"))
    ingested_at = _optional_timestamp(row.get("ingested_at"))
    available_at_source = row.get("available_at_source")

    hard_failures: list[HardFailureCode] = []
    warnings: list[str] = []

    if _uses_report_period_end_as_available_at(available_at, report_period_end, available_at_source):
        hard_failures.append(HardFailureCode.PIT_VIOLATION)
        warnings.append("report_period_end_used_as_available_at")

    if available_at is not None and available_at > as_of_ts:
        hard_failures.append(HardFailureCode.PIT_VIOLATION)
        warnings.append("available_at_after_as_of")

    conservative_proxy_at = (
        _conservative_proxy_available_at(announcement_time, trading_days) if announcement_time is not None else None
    )
    if ingested_at is not None and conservative_proxy_at is not None:
        if ingested_at > conservative_proxy_at and as_of_ts < ingested_at:
            hard_failures.append(HardFailureCode.PIT_VIOLATION)
            warnings.append("late_ingest_blocks_as_of")

    if hard_failures:
        effective_available_at = available_at if available_at is not None else conservative_proxy_at
        return FinancialQualityAvailabilityReport(
            mode=FinancialQualityAvailabilityMode.invalid,
            as_of=as_of_ts.to_pydatetime(),
            pit_safe=False,
            proxy_assumption=False,
            effective_available_at=effective_available_at.to_pydatetime()
            if effective_available_at is not None
            else None,
            hard_failures=_dedupe_failures(hard_failures),
            warnings=warnings,
            can_compute_factor_values=False,
            can_claim_alpha=False,
            data_audit_refs=["financial-quality-pit-gate"],
        )

    if available_at is not None:
        return FinancialQualityAvailabilityReport(
            mode=FinancialQualityAvailabilityMode.real_available_at,
            as_of=as_of_ts.to_pydatetime(),
            pit_safe=True,
            proxy_assumption=False,
            effective_available_at=available_at.to_pydatetime(),
            conclusion_cap=ConclusionLevel.exploratory,
            can_compute_factor_values=True,
            can_claim_alpha=False,
            data_audit_refs=["financial-quality-pit-gate"],
        )

    if conservative_proxy_at is not None:
        return FinancialQualityAvailabilityReport(
            mode=FinancialQualityAvailabilityMode.announcement_time_proxy,
            as_of=as_of_ts.to_pydatetime(),
            pit_safe=False,
            proxy_assumption=True,
            effective_available_at=conservative_proxy_at.to_pydatetime(),
            conclusion_cap=ConclusionLevel.exploratory,
            hard_failures=[HardFailureCode.AVAILABLE_AT_PROXY_ONLY],
            warnings=["announcement_time_proxy_only"],
            can_compute_factor_values=True,
            can_claim_alpha=False,
            data_audit_refs=["financial-quality-pit-gate"],
        )

    return FinancialQualityAvailabilityReport(
        mode=FinancialQualityAvailabilityMode.adapter_only,
        as_of=as_of_ts.to_pydatetime(),
        pit_safe=False,
        proxy_assumption=False,
        effective_available_at=None,
        conclusion_cap=ConclusionLevel.exploratory,
        warnings=["available_at_and_announcement_time_missing"],
        can_compute_factor_values=False,
        can_claim_alpha=False,
        data_audit_refs=["financial-quality-pit-gate"],
    )


def _optional_timestamp(value: object) -> pd.Timestamp | None:
    if value is None or pd.isna(value):
        return None
    return pd.Timestamp(value)


def _uses_report_period_end_as_available_at(
    available_at: pd.Timestamp | None,
    report_period_end: pd.Timestamp | None,
    available_at_source: object,
) -> bool:
    if available_at is None:
        return False
    if str(available_at_source or "").lower() == "report_period_end":
        return True
    if report_period_end is None:
        return False
    return available_at.normalize() == report_period_end.normalize()


def _conservative_proxy_available_at(
    announcement_time: pd.Timestamp,
    trading_days: list[pd.Timestamp] | pd.DatetimeIndex,
) -> pd.Timestamp:
    next_trading_day = add_trading_days(announcement_time, 1, trading_days)
    return next_trading_day.normalize() + pd.Timedelta(hours=15)


def _dedupe_failures(failures: list[HardFailureCode]) -> list[HardFailureCode]:
    deduped: list[HardFailureCode] = []
    for failure in failures:
        if failure not in deduped:
            deduped.append(failure)
    return deduped
