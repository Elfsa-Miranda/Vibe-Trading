from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from src.alpha_foundry.common.hashing import canonical_hash
from src.alpha_foundry.hypothesis.model import AlphaHypothesis
from src.alpha_foundry.hypothesis.registry import (
    AlphaHypothesisRegistry,
    RegistryValidationError,
)


REQUIRED_NON_FINANCIAL_IDS = {
    "limit_lock_strength",
    "limit_lock_persistence",
    "failed_limit_breakout_reversal",
    "post_limit_opening_pressure",
    "one_word_board_exclusion_alpha",
    "limit_gap_decay",
    "limit_down_liquidity_recovery",
    "limit_queue_pressure_proxy",
    "residual_20d_momentum",
    "liquidity_conditioned_reversal",
    "abnormal_turnover_unwind",
    "volume_price_divergence_reversal",
    "volatility_compression_breakout_quality",
}


def test_canonical_hash_is_stable_across_key_order_and_excludes_schema_version() -> None:
    left = {"schema_version": "2.1.0", "b": [2, 1], "a": {"z": 3, "y": "x"}}
    right = {"a": {"y": "x", "z": 3}, "b": [2, 1], "schema_version": "9.9.9"}

    assert canonical_hash(left) == canonical_hash(right)
    assert canonical_hash(left, exclude_schema_version=False) != canonical_hash(right, exclude_schema_version=False)


def test_canonical_hash_rejects_nan() -> None:
    with pytest.raises(ValueError, match="Out of range float values"):
        canonical_hash({"value": math.nan})


def test_default_registry_validates_all_required_hypotheses() -> None:
    registry = AlphaHypothesisRegistry.load_default()

    ids = {hypothesis.hypothesis_id for hypothesis in registry.list()}
    assert REQUIRED_NON_FINANCIAL_IDS.issubset(ids)

    for hypothesis in registry.list():
        assert hypothesis.required_data
        assert hypothesis.pit_requirements
        assert hypothesis.invalidation_conditions
        assert {
            "pit",
            "tradability",
            "neutralization",
            "regime",
            "cost",
            "oos",
        }.issubset(set(hypothesis.falsification_tests_required))

    queue_proxy = registry.get("limit_queue_pressure_proxy")
    assert queue_proxy.exploratory_only is True
    assert queue_proxy.proxy_note
    assert "Level-2" in queue_proxy.proxy_note


def test_bad_hypothesis_missing_required_gate_fails_clearly() -> None:
    with pytest.raises(ValidationError, match="falsification_tests_required"):
        AlphaHypothesis(
            hypothesis_id="bad_missing_oos",
            name="bad",
            track="limit_liquidity_microstructure",
            market_mechanism="limit mechanism",
            economic_rationale="rationale",
            required_data=["close"],
            pit_requirements=["bar_close"],
            tradability_constraints=["limit_state"],
            formation_window="1d",
            prediction_horizon="1d",
            expected_decay="short",
            direction="long",
            known_risks=["overfit"],
            crowding_risk="unknown",
            falsification_tests_required=["pit", "tradability", "neutralization", "regime", "cost"],
            invalidation_conditions=["fails oos"],
        )


def test_registry_rejects_duplicate_hypothesis_ids(tmp_path) -> None:
    duplicate_yaml = tmp_path / "registry.yaml"
    duplicate_yaml.write_text(
        """
hypotheses:
  - hypothesis_id: duplicate
    name: Duplicate 1
    track: limit_liquidity_microstructure
    market_mechanism: mechanism
    economic_rationale: rationale
    required_data: [close]
    pit_requirements: [bar_close]
    tradability_constraints: [limit_state]
    formation_window: 1d
    prediction_horizon: 1d
    expected_decay: short
    direction: long
    known_risks: [overfit]
    crowding_risk: unknown
    falsification_tests_required: [pit, tradability, neutralization, regime, cost, oos]
    invalidation_conditions: [fails]
  - hypothesis_id: duplicate
    name: Duplicate 2
    track: limit_liquidity_microstructure
    market_mechanism: mechanism
    economic_rationale: rationale
    required_data: [close]
    pit_requirements: [bar_close]
    tradability_constraints: [limit_state]
    formation_window: 1d
    prediction_horizon: 1d
    expected_decay: short
    direction: long
    known_risks: [overfit]
    crowding_risk: unknown
    falsification_tests_required: [pit, tradability, neutralization, regime, cost, oos]
    invalidation_conditions: [fails]
""",
        encoding="utf-8",
    )

    with pytest.raises(RegistryValidationError, match="duplicate hypothesis_id"):
        AlphaHypothesisRegistry.from_file(duplicate_yaml)


def test_registered_hypothesis_core_fields_are_immutable() -> None:
    registry = AlphaHypothesisRegistry.load_default()
    hypothesis = registry.get("failed_limit_breakout_reversal")

    with pytest.raises(ValidationError):
        hypothesis.market_mechanism = "changed"
