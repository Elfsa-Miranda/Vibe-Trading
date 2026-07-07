from __future__ import annotations

from datetime import date, timedelta

from src.alpha_foundry.forward.kill_rules import evaluate_forward_status
from src.alpha_foundry.forward.model import create_forward_observation, create_forward_tracking_plan


def _plan(min_observations_required: int = 12):
    return create_forward_tracking_plan(
        plan_id="plan-1",
        factor_id="residual_20d_momentum",
        hypothesis_id="residual_20d_momentum",
        frozen_factor_definition_hash="factor-hash",
        expected_rank_ic=0.03,
        min_observations_required=min_observations_required,
    )


def _observations(values: list[float]):
    obs = []
    start = date(2026, 1, 5)
    previous_hash = None
    for idx, value in enumerate(values):
        observation = create_forward_observation(
            observation_id=f"obs-{idx}",
            plan_id="plan-1",
            period_start=start + timedelta(days=idx * 7),
            period_end=start + timedelta(days=idx * 7 + 4),
            realized_rank_ic=value,
            previous_observation_hash=previous_hash,
        )
        previous_hash = observation.observation_hash
        obs.append(observation)
    return obs


def test_consecutive_negative_ic_kills_forward_plan() -> None:
    status = evaluate_forward_status(_plan(), _observations([0.01, -0.01, -0.02, -0.03]))

    assert status.status == "killed"
    assert "consecutive_negative_ic" in status.reasons


def test_no_paper_success_claim_before_min_observations() -> None:
    status = evaluate_forward_status(_plan(min_observations_required=12), _observations([0.05] * 5))

    assert status.status == "paper_tracking"
    assert "min_observations_not_met" in status.reasons

