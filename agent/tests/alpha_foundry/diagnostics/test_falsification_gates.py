from __future__ import annotations

import pandas as pd
import pytest

from src.alpha_foundry.common.errors import ConclusionLevel, HardFailureCode
from src.alpha_foundry.diagnostics.falsification import run_factor_falsification
from src.alpha_foundry.overfit.trial_ledger import TrialLedger


def _factor_and_returns(
    *,
    dates: int = 3,
    symbols: int = 35,
    factor_id: str = "residual_20d_momentum",
    return_column: str = "close_return",
    size_driven: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    factor_rows: list[dict[str, object]] = []
    return_rows: list[dict[str, object]] = []
    exposure_rows: list[dict[str, object]] = []
    for d in range(dates):
        day = pd.Timestamp("2026-01-05") + pd.Timedelta(days=d)
        for s in range(symbols):
            symbol = f"S{s:03d}"
            value = float(s)
            factor_value = value if size_driven else value + (d * 0.01)
            ret = value / 100.0
            factor_rows.append(
                {
                    "date": day,
                    "symbol": symbol,
                    "factor_value": factor_value,
                    "factor_id": factor_id,
                    "as_of": day + pd.Timedelta(hours=15),
                    "available_at": day + pd.Timedelta(hours=15),
                }
            )
            return_rows.append({"date": day, "symbol": symbol, return_column: ret})
            exposure_rows.append(
                {
                    "date": day,
                    "symbol": symbol,
                    "industry": "SW_BANK" if s % 2 == 0 else "SW_TECH",
                    "float_mktcap": 100.0 + (value if size_driven else 0.0),
                    "beta_60d": 1.0,
                    "log_avg_daily_turnover_20d": 2.0,
                }
            )
    return pd.DataFrame(factor_rows), pd.DataFrame(return_rows), pd.DataFrame(exposure_rows)


def _ledger(family_id: str = "residual_price_volume_behavior") -> TrialLedger:
    return TrialLedger.create(ledger_id=f"ledger-{family_id}", family_id=family_id)


def test_raw_ic_strong_but_neutralized_collapse_triggers_error_code() -> None:
    factor, returns, exposures = _factor_and_returns(size_driven=True)

    report, ledger = run_factor_falsification(
        factor,
        returns,
        factor_id="residual_20d_momentum",
        hypothesis_id="residual_20d_momentum",
        track="residual_price_volume_behavior",
        factor_definition_hash="factor-hash",
        protocol_hash="protocol-hash",
        ledger=_ledger(),
        exposures=exposures,
    )

    assert report.ic_raw > 0.9
    assert report.rank_ic_raw > 0.9
    assert abs(report.rank_ic_after_neutralization or 0.0) < 0.015
    assert HardFailureCode.NEUTRALIZED_IC_COLLAPSE in report.hard_failures
    assert report.falsified is True
    assert report.conclusion_cap == ConclusionLevel.exploratory
    assert ledger.trial_count(family_id="residual_price_volume_behavior", sub_family_id="residual_20d_momentum") == 1


def test_placebo_comparable_triggers_placebo_error_code() -> None:
    factor, returns, exposures = _factor_and_returns(size_driven=False)

    report, _ = run_factor_falsification(
        factor,
        returns,
        factor_id="residual_20d_momentum",
        hypothesis_id="residual_20d_momentum",
        track="residual_price_volume_behavior",
        factor_definition_hash="factor-hash",
        protocol_hash="protocol-hash",
        ledger=_ledger(),
        exposures=exposures,
        placebo_rank_ics=[0.997],
    )

    assert HardFailureCode.PLACEBO_COMPARABLE in report.hard_failures
    assert report.falsified is True
    assert report.conclusion_cap == ConclusionLevel.invalid


def test_limit_liquidity_requires_execution_return_for_tradable_validation() -> None:
    factor, returns, exposures = _factor_and_returns(
        factor_id="failed_limit_breakout_reversal",
        return_column="close_return",
    )

    report, _ = run_factor_falsification(
        factor,
        returns,
        factor_id="failed_limit_breakout_reversal",
        hypothesis_id="failed_limit_breakout_reversal",
        track="limit_liquidity_microstructure",
        factor_definition_hash="factor-hash",
        protocol_hash="protocol-hash",
        ledger=_ledger("limit_liquidity_microstructure"),
        exposures=exposures,
        return_column="close_return",
    )

    assert HardFailureCode.EXECUTION_RETURN_MISSING in report.hard_failures
    assert report.execution_return_used is False
    assert report.falsified is True


def test_positive_fixture_meets_research_candidate_metrics_and_appends_trial() -> None:
    factor, returns, exposures = _factor_and_returns(size_driven=False)

    report, ledger = run_factor_falsification(
        factor,
        returns,
        factor_id="residual_20d_momentum",
        hypothesis_id="residual_20d_momentum",
        track="residual_price_volume_behavior",
        factor_definition_hash="factor-hash",
        protocol_hash="protocol-hash",
        ledger=_ledger(),
        exposures=exposures,
    )

    assert report.rank_ic_after_neutralization is not None
    assert report.rank_ic_after_neutralization > 0.02
    assert report.t_stat_after_neutralization is not None
    assert report.t_stat_after_neutralization > 1.5
    assert report.falsified is False
    assert report.conclusion_cap == ConclusionLevel.research_candidate
    assert ledger.trial_count(family_id="residual_price_volume_behavior", sub_family_id="residual_20d_momentum") == 1


def test_trial_ledger_increments_for_each_falsification_report() -> None:
    factor, returns, exposures = _factor_and_returns(size_driven=False)
    ledger = _ledger()

    _, ledger = run_factor_falsification(
        factor,
        returns,
        factor_id="residual_20d_momentum",
        hypothesis_id="residual_20d_momentum",
        track="residual_price_volume_behavior",
        factor_definition_hash="factor-hash",
        protocol_hash="protocol-hash",
        ledger=ledger,
        exposures=exposures,
        parameter_variant={"window": 20},
    )
    _, ledger = run_factor_falsification(
        factor,
        returns,
        factor_id="residual_20d_momentum",
        hypothesis_id="residual_20d_momentum",
        track="residual_price_volume_behavior",
        factor_definition_hash="factor-hash",
        protocol_hash="protocol-hash",
        ledger=ledger,
        exposures=exposures,
        parameter_variant={"window": 40},
    )

    assert ledger.trial_count(family_id="residual_price_volume_behavior", sub_family_id="residual_20d_momentum") == 2
    assert {record.outcome for record in ledger.records} == {"selected"}
    assert all(record.report_ref for record in ledger.records)


def test_negative_fixture_is_falsified_with_explicit_error_code() -> None:
    factor, returns, exposures = _factor_and_returns(size_driven=False)

    report, _ = run_factor_falsification(
        factor,
        returns,
        factor_id="residual_20d_momentum",
        hypothesis_id="residual_20d_momentum",
        track="residual_price_volume_behavior",
        factor_definition_hash="factor-hash",
        protocol_hash="protocol-hash",
        ledger=_ledger(),
        exposures=exposures,
        placebo_rank_ics=[1.0],
    )

    assert report.falsified is True
    assert report.hard_failures == [HardFailureCode.PLACEBO_COMPARABLE]

