from __future__ import annotations

import pandas as pd
import pytest

from src.alpha_foundry.factors.base import factor_definition_hash
from src.alpha_foundry.factors.price_volume import (
    PRICE_VOLUME_FACTOR_IDS,
    PriceVolumeInputFrameError,
    compute_price_volume_factor,
    compute_price_volume_factors,
    get_price_volume_factor_metadata,
    get_price_volume_specs,
)
from src.alpha_foundry.panels.interfaces import FACTOR_OUTPUT_COLUMNS, validate_factor_output_frame
from tests.alpha_foundry.fixtures.factory import make_price_volume_factor_input_frame


CURRENT_DATE = pd.Timestamp("2026-01-05")


def _subset(symbols: list[str]) -> pd.DataFrame:
    frame = make_price_volume_factor_input_frame()
    return frame[frame["symbol"].isin(symbols)].reset_index(drop=True)


def _current_value(output: pd.DataFrame, symbol: str) -> float:
    row = output[(output["date"] == CURRENT_DATE) & (output["symbol"] == symbol)]
    assert len(row) == 1
    return float(row.iloc[0]["factor_value"])


def _assert_clean_output(output: pd.DataFrame, factor_id: str) -> None:
    clean = validate_factor_output_frame(output)
    assert list(clean.columns) == FACTOR_OUTPUT_COLUMNS
    assert set(clean["factor_id"]) == {factor_id}


def test_all_price_volume_factors_emit_clean_factor_output_frames() -> None:
    outputs = compute_price_volume_factors(make_price_volume_factor_input_frame())

    assert set(outputs) == set(PRICE_VOLUME_FACTOR_IDS)
    for factor_id, output in outputs.items():
        _assert_clean_output(output, factor_id)


@pytest.mark.parametrize(
    ("factor_id", "symbols", "expected"),
    [
        ("residual_20d_momentum", ["RES_A", "RES_B", "RES_C"], {"RES_A": 0.06, "RES_B": 0.0, "RES_C": -0.06}),
        ("liquidity_conditioned_reversal", ["LIQ_A", "LIQ_B", "LIQ_C"], {"LIQ_A": -0.04, "LIQ_B": 0.03, "LIQ_C": 0.0}),
        ("abnormal_turnover_unwind", ["ABN_A", "ABN_B"], {"ABN_A": -1.0, "ABN_B": -0.25}),
        ("volume_price_divergence_reversal", ["DIV_A", "DIV_B"], {"DIV_A": -1.0, "DIV_B": 0.5}),
        ("volatility_compression_breakout_quality", ["VOL_A", "VOL_B"], {"VOL_A": 1.0, "VOL_B": 0.0}),
    ],
)
def test_price_volume_factor_values_are_deterministic(
    factor_id: str,
    symbols: list[str],
    expected: dict[str, float],
) -> None:
    output = compute_price_volume_factor(_subset(symbols), factor_id)

    _assert_clean_output(output, factor_id)
    for symbol, expected_value in expected.items():
        assert _current_value(output, symbol) == pytest.approx(expected_value)


def test_direction_metadata_matches_hypothesis_specs() -> None:
    directions = {
        factor_id: get_price_volume_factor_metadata(factor_id).default_direction
        for factor_id in PRICE_VOLUME_FACTOR_IDS
    }

    assert directions == {
        "residual_20d_momentum": "long",
        "liquidity_conditioned_reversal": "long_short",
        "abnormal_turnover_unwind": "short",
        "volume_price_divergence_reversal": "long_short",
        "volatility_compression_breakout_quality": "long",
    }


def test_residual_basis_metadata_is_fixed_without_ic_or_alpha_claims() -> None:
    metadata = get_price_volume_factor_metadata("residual_20d_momentum")

    assert metadata.residual_basis == {
        "industry_classification": "SW_L1",
        "market_cap": "float_mktcap",
        "beta": "60 trading days vs CSI_500",
        "liquidity_proxy": "log_avg_daily_turnover_20d",
        "regression": "cross_sectional_WLS",
        "outlier_treatment": "winsorize 1%-99%",
        "min_cross_section_size": 30,
    }
    assert metadata.claims_neutralized_ic is False
    assert metadata.claims_alpha_validity is False


def test_transform_pipeline_order_changes_price_volume_hash() -> None:
    spec = get_price_volume_specs()["residual_20d_momentum"]
    reversed_spec = spec.model_copy(update={"transform_pipeline": list(reversed(spec.transform_pipeline))})

    assert factor_definition_hash(spec) != factor_definition_hash(reversed_spec)


def test_forbidden_future_fields_are_rejected_before_price_volume_computation() -> None:
    frame = _subset(["DIV_A"])
    frame["forward_return"] = 0.01

    with pytest.raises(PriceVolumeInputFrameError, match="forbidden"):
        compute_price_volume_factor(frame, "volume_price_divergence_reversal")

