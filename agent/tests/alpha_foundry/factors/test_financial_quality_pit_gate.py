from __future__ import annotations

import pandas as pd

from src.alpha_foundry.common.errors import ConclusionLevel, HardFailureCode
from src.alpha_foundry.factors.financial_quality import (
    DATA_AVAILABILITY_MATRIX_REF,
    FinancialQualityAvailabilityMode,
    assess_financial_quality_availability,
)


AS_OF = pd.Timestamp("2026-01-07 15:00:00")
TRADING_DAYS = [
    pd.Timestamp("2026-01-05"),
    pd.Timestamp("2026-01-06"),
    pd.Timestamp("2026-01-07"),
    pd.Timestamp("2026-01-08"),
]


def _frame(**overrides: object) -> pd.DataFrame:
    base: dict[str, object] = {
        "date": pd.Timestamp("2026-01-07"),
        "symbol": "000001.SZ",
        "profitability": 0.12,
        "announcement_time": pd.Timestamp("2026-01-05 20:00:00"),
        "available_at": pd.Timestamp("2026-01-06 15:00:00"),
        "available_at_source": "real_available_at",
        "report_period_end": pd.Timestamp("2025-12-31"),
        "ingested_at": pd.Timestamp("2026-01-06 10:00:00"),
    }
    base.update(overrides)
    return pd.DataFrame([base])


def test_report_period_end_as_available_at_hard_fails() -> None:
    report = assess_financial_quality_availability(
        _frame(
            available_at=pd.Timestamp("2025-12-31"),
            available_at_source="report_period_end",
        ),
        as_of=AS_OF,
        trading_days=TRADING_DAYS,
    )

    assert report.mode == FinancialQualityAvailabilityMode.invalid
    assert HardFailureCode.PIT_VIOLATION in report.hard_failures
    assert report.pit_safe is False
    assert report.can_claim_alpha is False
    assert report.data_availability_matrix_ref == DATA_AVAILABILITY_MATRIX_REF


def test_available_at_after_as_of_hard_fails() -> None:
    report = assess_financial_quality_availability(
        _frame(available_at=pd.Timestamp("2026-01-08 15:00:00")),
        as_of=AS_OF,
        trading_days=TRADING_DAYS,
    )

    assert report.mode == FinancialQualityAvailabilityMode.invalid
    assert HardFailureCode.PIT_VIOLATION in report.hard_failures
    assert "available_at_after_as_of" in report.warnings


def test_announcement_time_proxy_caps_exploratory_and_is_not_pit_safe() -> None:
    report = assess_financial_quality_availability(
        _frame(available_at=pd.NaT, available_at_source=None),
        as_of=AS_OF,
        trading_days=TRADING_DAYS,
    )

    assert report.mode == FinancialQualityAvailabilityMode.announcement_time_proxy
    assert report.effective_available_at == pd.Timestamp("2026-01-06 15:00:00")
    assert report.proxy_assumption is True
    assert report.pit_safe is False
    assert report.conclusion_cap == ConclusionLevel.exploratory
    assert HardFailureCode.AVAILABLE_AT_PROXY_ONLY in report.hard_failures
    assert report.can_claim_alpha is False


def test_ingested_at_after_announcement_blocks_as_of() -> None:
    report = assess_financial_quality_availability(
        _frame(
            available_at=pd.Timestamp("2026-01-06 15:00:00"),
            ingested_at=pd.Timestamp("2026-01-08 10:00:00"),
        ),
        as_of=AS_OF,
        trading_days=TRADING_DAYS,
    )

    assert report.mode == FinancialQualityAvailabilityMode.invalid
    assert HardFailureCode.PIT_VIOLATION in report.hard_failures
    assert "late_ingest_blocks_as_of" in report.warnings


def test_adapter_only_when_no_available_or_announcement_time() -> None:
    report = assess_financial_quality_availability(
        _frame(
            available_at=pd.NaT,
            available_at_source=None,
            announcement_time=pd.NaT,
        ),
        as_of=AS_OF,
        trading_days=TRADING_DAYS,
    )

    assert report.mode == FinancialQualityAvailabilityMode.adapter_only
    assert report.can_compute_factor_values is False
    assert report.can_claim_alpha is False
    assert report.pit_safe is False
    assert report.conclusion_cap == ConclusionLevel.exploratory
    assert report.data_availability_matrix_ref == "docs/aaf-v2-data-availability-matrix.md"

