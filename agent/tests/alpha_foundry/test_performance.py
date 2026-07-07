from __future__ import annotations

import time

import pandas as pd

from src.alpha_foundry.diagnostics.falsification import run_factor_falsification
from src.alpha_foundry.overfit.trial_ledger import TrialLedger


def _fixture(factor_id: str, horizon: int) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    factor_rows: list[dict[str, object]] = []
    return_rows: list[dict[str, object]] = []
    exposure_rows: list[dict[str, object]] = []
    for d in range(3):
        day = pd.Timestamp("2026-01-05") + pd.Timedelta(days=d)
        for s in range(35):
            symbol = f"S{s:03d}"
            value = float(s + horizon)
            factor_rows.append(
                {
                    "date": day,
                    "symbol": symbol,
                    "factor_value": value,
                    "factor_id": factor_id,
                    "as_of": day + pd.Timedelta(hours=15),
                    "available_at": day + pd.Timedelta(hours=15),
                }
            )
            return_rows.append({"date": day, "symbol": symbol, "close_return": value / 100.0})
            exposure_rows.append(
                {
                    "date": day,
                    "symbol": symbol,
                    "industry": "SW_BANK" if s % 2 == 0 else "SW_TECH",
                    "float_mktcap": 100.0,
                    "beta_60d": 1.0,
                    "log_avg_daily_turnover_20d": 2.0,
                }
            )
    return pd.DataFrame(factor_rows), pd.DataFrame(return_rows), pd.DataFrame(exposure_rows)


def test_falsification_performance_smoke() -> None:
    ledger = TrialLedger.create(
        ledger_id="ledger-performance",
        family_id="residual_price_volume_behavior",
    )
    started = time.perf_counter()

    for factor_idx in range(20):
        for horizon in (1, 3, 5, 10, 20):
            factor_id = f"fixture_factor_{factor_idx:02d}_{horizon}"
            factor, returns, exposures = _fixture(factor_id, horizon)
            _, ledger = run_factor_falsification(
                factor,
                returns,
                factor_id=factor_id,
                hypothesis_id="residual_20d_momentum",
                track="residual_price_volume_behavior",
                factor_definition_hash=f"hash-{factor_id}",
                protocol_hash="protocol-hash",
                ledger=ledger,
                exposures=exposures,
                parameter_variant={"horizon": horizon},
            )

    elapsed = time.perf_counter() - started
    assert ledger.trial_count(family_id="residual_price_volume_behavior") == 100
    assert elapsed < 5.0

