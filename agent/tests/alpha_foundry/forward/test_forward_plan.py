from __future__ import annotations

import pytest

from src.alpha_foundry.forward.model import (
    ForwardPlanConfigMutationError,
    assert_forward_plan_config_unchanged,
    create_forward_tracking_plan,
)


def test_forward_plan_requires_frozen_hashes_and_min_observations() -> None:
    plan = create_forward_tracking_plan(
        plan_id="plan-1",
        factor_id="residual_20d_momentum",
        hypothesis_id="residual_20d_momentum",
        frozen_factor_definition_hash="factor-hash",
        expected_rank_ic=0.03,
        signal_half_life_observation_periods=8,
    )

    assert plan.frozen_factor_definition_hash == "factor-hash"
    assert plan.frozen_config_hash
    assert plan.min_observations_required == 16
    assert plan.kill_rule_params["consecutive_negative_ic_n"] == 3


def test_changing_kill_rule_params_changes_hash_and_is_rejected_after_plan_start() -> None:
    plan = create_forward_tracking_plan(
        plan_id="plan-1",
        factor_id="residual_20d_momentum",
        hypothesis_id="residual_20d_momentum",
        frozen_factor_definition_hash="factor-hash",
        expected_rank_ic=0.03,
    )
    changed_params = dict(plan.kill_rule_params)
    changed_params["consecutive_negative_ic_n"] = 4

    with pytest.raises(ForwardPlanConfigMutationError):
        assert_forward_plan_config_unchanged(plan, changed_params)

