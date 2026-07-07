from __future__ import annotations

import pandas as pd

from src.alpha_foundry.portfolio.combine import assess_orthogonal_alpha


def test_high_correlation_without_marginal_ic_rejects_incremental_alpha() -> None:
    frame = pd.DataFrame(
        {
            "date": pd.Timestamp("2026-01-05"),
            "symbol": [f"S{i:03d}" for i in range(40)],
            "candidate": list(range(40)),
            "existing_alpha": [value * 1.01 for value in range(40)],
        }
    )

    report = assess_orthogonal_alpha(
        frame,
        candidate_column="candidate",
        existing_factor_columns=["existing_alpha"],
        marginal_ic_after_existing=0.0,
    )

    assert report.accepted is False
    assert report.max_abs_correlation > 0.65
    assert report.orthogonalization_required is True
    assert "high_correlation_no_marginal_ic" in report.warnings

