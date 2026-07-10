from __future__ import annotations

import pytest

from src.alpha_quality.falsification.dependence import hac_mean, moving_block_bootstrap_mean, nonoverlapping_mean


def test_overlapping_horizon_uses_declared_hac_or_nonoverlap_method() -> None:
    values = [0.1, 0.2, -0.1, 0.3, 0.0, 0.2, 0.1, -0.2]
    hac = hac_mean(values, max_lag=2)
    nonoverlap = nonoverlapping_mean(values, horizon=2)
    assert hac.method == "hac_bartlett_lag_2"
    assert nonoverlap.method == "nonoverlap_horizon_2"
    assert hac.standard_error >= 0 and nonoverlap.standard_error >= 0


def test_block_bootstrap_is_seeded_and_reproducible() -> None:
    values = [float(index) for index in range(20)]
    left = moving_block_bootstrap_mean(values, block_length=4, replicates=50, seed=17)
    right = moving_block_bootstrap_mean(values, block_length=4, replicates=50, seed=17)
    assert left == right
    assert len(left) == 50
    assert left != moving_block_bootstrap_mean(values, block_length=4, replicates=50, seed=18)


def test_nonfinite_dependence_input_is_rejected() -> None:
    with pytest.raises(ValueError, match="finite"):
        hac_mean([0.1, float("inf")], max_lag=0)
