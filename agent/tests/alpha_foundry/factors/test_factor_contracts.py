from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.alpha_foundry.common.errors import ConclusionLevel
from src.alpha_foundry.factors.base import (
    FactorFormulaSpec,
    FactorSpec,
    TransformStep,
    factor_definition_hash,
    load_factor_specs,
)


def _formula(formula_id: str = "test_formula") -> FactorFormulaSpec:
    return FactorFormulaSpec(
        formula_id=formula_id,
        formula_version="1.0",
        pseudocode="rank(close / prev_close - 1)",
        required_fields=["close", "prev_close"],
        forbidden_fields=["forward_return", "future_close", "execution_return"],
        signal_time="T close",
        data_availability_policy="bar_close_derived",
        formula_hash="formula-hash",
    )


def _factor_spec(transform_pipeline: list[TransformStep]) -> FactorSpec:
    return FactorSpec(
        factor_id="test_factor",
        hypothesis_id="limit_lock_strength",
        track="limit_liquidity_microstructure",
        formula=_formula(),
        transform_pipeline=transform_pipeline,
        universe_policy="CSI_500_like_fixture",
        tradability_policy="a_share_default",
        prediction_horizons=[1, 5],
        benchmark="CSI_500",
        default_direction="long",
        conclusion_cap=ConclusionLevel.exploratory,
    )


def test_transform_pipeline_order_changes_hash() -> None:
    winsorize = TransformStep(step="winsorize", params={"lower": 0.01, "upper": 0.99})
    zscore = TransformStep(step="zscore", params={"by": "date"})

    first = _factor_spec([winsorize, zscore])
    second = _factor_spec([zscore, winsorize])

    assert factor_definition_hash(first) != factor_definition_hash(second)


def test_factor_spec_rejects_unordered_transformation_field() -> None:
    payload = _factor_spec([TransformStep(step="rank")]).model_dump(mode="json")
    payload["transformation"] = ["rank", "zscore"]

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        FactorSpec.model_validate(payload)


def test_formula_yaml_specs_include_required_metadata() -> None:
    specs = []
    for name in ("limit_liquidity", "price_volume", "financial_quality"):
        specs.extend(load_factor_specs(name))

    assert {spec.factor_id for spec in specs} >= {
        "limit_lock_strength",
        "limit_queue_pressure_proxy",
        "residual_20d_momentum",
        "pit_profitability_acceleration",
    }

    for spec in specs:
        assert spec.formula.pseudocode
        assert spec.formula.required_fields
        assert {"forward_return", "future_close", "future_volume", "next_day_tradability_outcome"}.issubset(
            set(spec.formula.forbidden_fields)
        )
        assert spec.formula.signal_time
        assert spec.formula.data_availability_policy
        assert spec.formula.formula_hash

    queue_spec = next(spec for spec in specs if spec.factor_id == "limit_queue_pressure_proxy")
    assert queue_spec.formula.proxy_note
    assert queue_spec.conclusion_cap == ConclusionLevel.exploratory
