from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from src.alpha_foundry.common.errors import ConclusionLevel
from src.alpha_foundry.factors.limit_liquidity import (
    LIMIT_LIQUIDITY_FACTOR_IDS,
    FactorInputFrameError,
    build_limit_liquidity_execution_mask,
    compute_limit_liquidity_factor,
    compute_limit_liquidity_factors,
    get_limit_liquidity_factor_metadata,
)
from src.alpha_foundry.panels.interfaces import FACTOR_OUTPUT_COLUMNS, validate_factor_output_frame
from tests.alpha_foundry.fixtures.factory import make_limit_liquidity_factor_input_frame


CURRENT_DATE = pd.Timestamp("2026-01-05")


def _subset(symbols: list[str]) -> pd.DataFrame:
    frame = make_limit_liquidity_factor_input_frame()
    return frame[frame["symbol"].isin(symbols)].reset_index(drop=True)


def _current_value(output: pd.DataFrame, symbol: str) -> float:
    row = output[(output["date"] == CURRENT_DATE) & (output["symbol"] == symbol)]
    assert len(row) == 1
    return float(row.iloc[0]["factor_value"])


def _assert_clean_output(output: pd.DataFrame, factor_id: str) -> None:
    clean = validate_factor_output_frame(output)
    assert list(clean.columns) == FACTOR_OUTPUT_COLUMNS
    assert set(clean["factor_id"]) == {factor_id}


def test_all_limit_liquidity_factors_emit_clean_factor_output_frames() -> None:
    outputs = compute_limit_liquidity_factors(make_limit_liquidity_factor_input_frame())

    assert set(outputs) == set(LIMIT_LIQUIDITY_FACTOR_IDS)
    for factor_id, output in outputs.items():
        _assert_clean_output(output, factor_id)


@pytest.mark.parametrize(
    ("factor_id", "symbols", "expected"),
    [
        ("limit_lock_strength", ["LOCK", "FRESH"], {"LOCK": 1.6, "FRESH": 0.5}),
        ("limit_lock_persistence", ["LOCK", "FRESH"], {"LOCK": 2 / 3, "FRESH": 1 / 3}),
        ("failed_limit_breakout_reversal", ["BREAK"], {"BREAK": -1.0}),
        ("post_limit_opening_pressure", ["PRESS_A", "PRESS_B"], {"PRESS_A": 1.0, "PRESS_B": 0.25}),
        ("one_word_board_exclusion_alpha", ["OWB", "NORMAL"], {"OWB": 1.0, "NORMAL": 0.0}),
        ("limit_gap_decay", ["GAP_A", "GAP_B"], {"GAP_A": 0.5, "GAP_B": -0.5}),
        ("limit_down_liquidity_recovery", ["DOWN_A", "DOWN_B"], {"DOWN_A": 1.0, "DOWN_B": 0.25}),
        ("limit_queue_pressure_proxy", ["QUEUE"], {"QUEUE": 0.8}),
    ],
)
def test_limit_liquidity_factor_values_are_deterministic(
    factor_id: str,
    symbols: list[str],
    expected: dict[str, float],
) -> None:
    output = compute_limit_liquidity_factor(_subset(symbols), factor_id)

    _assert_clean_output(output, factor_id)
    for symbol, expected_value in expected.items():
        assert _current_value(output, symbol) == pytest.approx(expected_value)


def test_eod_queue_proxy_cannot_be_promoted_to_research_candidate() -> None:
    metadata = get_limit_liquidity_factor_metadata("limit_queue_pressure_proxy", level2_available=False)

    assert metadata.exploratory_only is True
    assert metadata.conclusion_cap == ConclusionLevel.exploratory
    assert metadata.can_claim_level2_queue_alpha is False
    assert metadata.proxy_note is not None
    assert "Level-2" in metadata.proxy_note


def test_one_word_board_exclusion_mask_removes_untradable_winners_from_execution_sample() -> None:
    frame = _subset(["OWB", "NORMAL"])

    execution_mask = build_limit_liquidity_execution_mask(frame, as_of=date(2026, 1, 5))
    output = compute_limit_liquidity_factor(frame, "one_word_board_exclusion_alpha")

    assert execution_mask["OWB"] is False
    assert execution_mask["NORMAL"] is True
    assert _current_value(output, "OWB") == 1.0
    assert _current_value(output, "NORMAL") == 0.0


def test_limit_day_universe_keeps_limit_up_names_in_factor_sample() -> None:
    output = compute_limit_liquidity_factor(_subset(["LOCK", "FRESH", "NORMAL"]), "limit_lock_strength")
    current_symbols = set(output.loc[output["date"] == CURRENT_DATE, "symbol"])

    assert {"LOCK", "FRESH", "NORMAL"} <= current_symbols
    assert _current_value(output, "LOCK") > 0
    assert _current_value(output, "FRESH") > 0


def test_forbidden_future_fields_are_rejected_before_factor_computation() -> None:
    frame = _subset(["LOCK"])
    frame["execution_return"] = 0.01

    with pytest.raises(FactorInputFrameError, match="forbidden"):
        compute_limit_liquidity_factor(frame, "limit_lock_strength")

