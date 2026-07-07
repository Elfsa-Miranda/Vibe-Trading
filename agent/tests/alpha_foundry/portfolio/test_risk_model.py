from __future__ import annotations

from datetime import date

import numpy as np

from src.alpha_foundry.common.errors import HardFailureCode
from src.alpha_foundry.portfolio.risk_model import (
    RiskModelSpec,
    build_risk_model_snapshot,
    covariance_is_psd,
    validate_portfolio_candidate_gate,
)


def test_risk_model_snapshot_repairs_covariance_to_psd() -> None:
    non_psd = np.array([[1.0, 2.0], [2.0, 1.0]])

    snapshot = build_risk_model_snapshot(
        model_id="risk-fixture",
        as_of=date(2026, 1, 5),
        universe=["S001", "S002"],
        factor_names=["market", "size"],
        factor_covariance_matrix=non_psd,
        residual_variance={"S001": 0.1, "S002": 0.1},
        estimation_window_days=60,
        repair_non_psd=True,
    )

    repaired = np.array([[snapshot.factor_covariance[a][b] for b in snapshot.factor_names] for a in snapshot.factor_names])
    assert snapshot.covariance_psd is True
    assert covariance_is_psd(repaired)
    assert "covariance_repaired_by_eigenvalue_clipping" in snapshot.warnings


def test_risk_model_missing_or_non_psd_blocks_portfolio_candidate() -> None:
    failures = validate_portfolio_candidate_gate(None, benchmark_id="CSI_500_EW")

    assert HardFailureCode.RISK_MODEL_MISSING in failures

    snapshot = build_risk_model_snapshot(
        model_id="risk-bad",
        as_of=date(2026, 1, 5),
        universe=["S001", "S002"],
        factor_names=["market", "size"],
        factor_covariance_matrix=np.array([[1.0, 2.0], [2.0, 1.0]]),
        residual_variance={"S001": 0.1, "S002": 0.1},
        estimation_window_days=60,
        repair_non_psd=False,
    )
    failures = validate_portfolio_candidate_gate(snapshot, benchmark_id=None)

    assert HardFailureCode.RISK_MODEL_NOT_PSD in failures
    assert HardFailureCode.BENCHMARK_MISSING in failures


def test_risk_model_spec_defaults_match_a_share_standard() -> None:
    spec = RiskModelSpec()

    assert spec.industry_classification == "SW_L1"
    assert spec.market_cap_field == "float_mktcap"
    assert spec.beta_benchmark == "CSI_500"
    assert spec.beta_window_days == 60
    assert spec.liquidity_proxy == "log_avg_daily_turnover_20d"

