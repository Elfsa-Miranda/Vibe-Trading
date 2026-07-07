from __future__ import annotations

import pandas as pd

from src.alpha_foundry.common.errors import HardFailureCode
from src.alpha_foundry.portfolio.optimizer import PortfolioConstraints, construct_long_only_top_n_portfolio
from src.alpha_foundry.portfolio.risk_model import validate_portfolio_candidate_gate


def _scores() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": ["S001", "S002", "S003", "S004"],
            "score": [0.9, 0.8, 0.7, 0.1],
            "sector": ["bank", "bank", "tech", "tech"],
            "adv": [10_000_000.0, 10_000_000.0, 10_000_000.0, 10_000_000.0],
            "price": [10.0, 20.0, 25.0, 40.0],
        }
    )


def test_optimizer_respects_single_name_sector_turnover_adv_and_lot_caps() -> None:
    constraints = PortfolioConstraints(
        top_n=3,
        single_name_cap=0.30,
        sector_cap=0.50,
        turnover_cap=0.80,
        adv_cap=0.05,
        benchmark_id="CSI_500_EW",
        portfolio_notional=1_000_000.0,
    )
    previous = {"S001": 0.20, "S002": 0.10, "S003": 0.10}

    report = construct_long_only_top_n_portfolio(_scores(), constraints=constraints, previous_weights=previous)

    assert report.hard_failures == []
    assert max(report.weights.values()) <= 0.30
    assert report.sector_weights["bank"] <= 0.50
    assert report.turnover is not None and report.turnover <= 0.80
    assert max(report.adv_participation.values()) <= 0.05
    assert all(shares % 100 == 0 for shares in report.shares.values())
    assert "optimizer_mvp_not_production" in report.warnings


def test_benchmark_missing_blocks_alpha_or_portfolio_claim() -> None:
    assert HardFailureCode.BENCHMARK_MISSING in validate_portfolio_candidate_gate(None, benchmark_id=None)

