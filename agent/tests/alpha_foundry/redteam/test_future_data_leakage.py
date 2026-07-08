from __future__ import annotations

import pytest

from src.alpha_foundry.factors.limit_liquidity import (
    FactorInputFrameError,
    compute_limit_liquidity_factor,
)
from src.alpha_foundry.factors.price_volume import (
    PriceVolumeInputFrameError,
    compute_price_volume_factor,
)
from tests.alpha_foundry.fixtures.factory import (
    make_limit_liquidity_factor_input_frame,
    make_price_volume_factor_input_frame,
)


@pytest.mark.parametrize("leak_column", ["next_close", "future_tradability", "execution_return"])
def test_limit_liquidity_factor_compute_rejects_future_data_columns(leak_column: str) -> None:
    frame = make_limit_liquidity_factor_input_frame()
    frame[leak_column] = 1.0

    with pytest.raises(FactorInputFrameError, match="forbidden"):
        compute_limit_liquidity_factor(frame, "limit_lock_strength")


@pytest.mark.parametrize("leak_column", ["next_close", "future_volume", "execution_return"])
def test_price_volume_factor_compute_rejects_future_data_columns(leak_column: str) -> None:
    frame = make_price_volume_factor_input_frame()
    frame[leak_column] = 1.0

    with pytest.raises(PriceVolumeInputFrameError, match="forbidden"):
        compute_price_volume_factor(frame, "residual_20d_momentum")
