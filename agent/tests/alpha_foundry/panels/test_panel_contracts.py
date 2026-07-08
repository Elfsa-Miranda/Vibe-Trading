from __future__ import annotations

from datetime import date

import pandas as pd
import pytest
from pydantic import ValidationError

from src.alpha_foundry.panels.alignment import add_trading_days
from src.alpha_foundry.panels.factor_panel import FactorPanelContract
from src.alpha_foundry.panels.forward_returns import (
    ForwardReturnContract,
    require_execution_return_for_track,
    validate_forward_return_frame,
)
from src.alpha_foundry.panels.interfaces import (
    FACTOR_OUTPUT_COLUMNS,
    FactorOutputFrameError,
    validate_factor_output_frame,
)
from src.alpha_foundry.panels.tradability import build_tradability_mask
from tests.alpha_foundry.fixtures.factory import (
    make_factor_output_frame,
    make_forward_return_frame,
    make_tradability_input_frame,
)
from tests.alpha_foundry.fixtures.scenarios import TRADING_DAYS


def test_factor_output_frame_rejects_future_return_columns() -> None:
    frame = make_factor_output_frame()
    frame["forward_return"] = 0.01

    with pytest.raises(FactorOutputFrameError, match="forbidden"):
        validate_factor_output_frame(frame)


def test_factor_output_frame_requires_range_index() -> None:
    frame = make_factor_output_frame().set_index(["date", "symbol"])

    with pytest.raises(FactorOutputFrameError, match="RangeIndex"):
        validate_factor_output_frame(frame)


def test_factor_output_frame_has_only_clean_columns() -> None:
    frame = validate_factor_output_frame(make_factor_output_frame())

    assert list(frame.columns) == [
        "date",
        "symbol",
        "factor_id",
        "factor_value",
        "as_of",
        "signal_time",
        "available_at",
        "data_availability_policy",
        "factor_definition_hash",
    ]
    assert list(frame.columns) == FACTOR_OUTPUT_COLUMNS


def test_factor_panel_requires_protocol_hash_when_tested() -> None:
    with pytest.raises(ValidationError, match="protocol_hash"):
        FactorPanelContract(
            panel_id="panel-tested",
            hypothesis_ids=["limit_lock_strength"],
            factor_ids=["limit_lock_strength"],
            as_of_policy="T close",
            coverage_by_date={"2026-01-05": 0.9},
            universe_ref="fixture-universe",
            data_audit_refs=["audit-1"],
            factor_definition_hashes={"limit_lock_strength": "hash-1"},
            implementation_status="tested",
        )


def test_coverage_below_60_warns_and_below_30_drops() -> None:
    panel = FactorPanelContract(
        panel_id="panel-draft",
        hypothesis_ids=["limit_lock_strength"],
        factor_ids=["limit_lock_strength"],
        as_of_policy="T close",
        coverage_by_date={
            "2026-01-05": 0.75,
            "2026-01-06": 0.50,
            "2026-01-07": 0.20,
        },
        universe_ref="fixture-universe",
        data_audit_refs=["audit-1"],
        factor_definition_hashes={"limit_lock_strength": "hash-1"},
    )

    assert panel.coverage_warnings() == [
        "coverage below warn threshold on 2026-01-06: 0.5000",
        "coverage below drop threshold on 2026-01-07: 0.2000",
    ]
    assert panel.ic_eligible_dates() == ["2026-01-05", "2026-01-06"]


def test_forward_return_has_close_and_execution_return() -> None:
    frame = validate_forward_return_frame(make_forward_return_frame())

    assert {"close_return", "execution_return"}.issubset(set(frame.columns))


def test_limit_liquidity_requires_execution_return() -> None:
    contract = ForwardReturnContract(
        horizon_days=1,
        uses_execution_return=False,
        execution_price_policy="close_only_reference",
        t_plus_one_policy="not_applied",
        limit_state_policy="not_applied",
        suspension_policy="not_applied",
    )

    with pytest.raises(ValueError, match="execution_return"):
        require_execution_return_for_track("limit_liquidity_microstructure", contract)


def test_st_mask_uses_announcement_date_with_t1_lag() -> None:
    input_frame = make_tradability_input_frame()

    same_day = build_tradability_mask(input_frame, as_of=date(2026, 1, 5))
    next_day = build_tradability_mask(input_frame, as_of=date(2026, 1, 6))

    assert same_day.masks["ST001"]["st"] is True
    assert same_day.masks["ST001"]["tradable"] is True
    assert next_day.masks["ST001"]["st"] is False
    assert next_day.masks["ST001"]["tradable"] is False


def test_tradability_mask_covers_a_share_market_rules() -> None:
    report = build_tradability_mask(make_tradability_input_frame(), as_of=date(2026, 1, 6))

    assert report.lot_size_policy == "100_shares"
    assert report.masks["LUP001"]["limit_up"] is False
    assert report.masks["SUS001"]["suspension"] is False
    assert report.masks["ST001"]["st"] is False
    assert report.masks["NEW001"]["new_stock"] is False
    assert report.masks["OWB001"]["one_word_board"] is False
    assert report.tradable_count == 1


def test_holiday_alignment_uses_trading_days_not_calendar_days() -> None:
    assert add_trading_days(pd.Timestamp("2026-01-02"), 1, TRADING_DAYS) == pd.Timestamp("2026-01-05")
    assert add_trading_days(pd.Timestamp("2026-01-02"), 2, TRADING_DAYS) == pd.Timestamp("2026-01-06")
