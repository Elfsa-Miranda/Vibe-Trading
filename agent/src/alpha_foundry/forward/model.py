"""Forward tracking models and frozen config helpers."""

from __future__ import annotations

from datetime import date, datetime, timezone
from math import ceil
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.alpha_foundry.common.hashing import canonical_hash


DEFAULT_KILL_RULE_PARAMS = {
    "consecutive_negative_ic_n": 3,
    "ic_decay_threshold_pct": 0.30,
    "realized_vs_expected_ratio_min": 0.30,
}


class ForwardPlanConfigMutationError(ValueError):
    """Raised when frozen forward plan config is changed after start."""


class ForwardTrackingPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "2.1.0"
    plan_id: str
    factor_id: str
    hypothesis_id: str
    accepted_at: datetime
    frozen_factor_definition_hash: str
    frozen_config_hash: str
    observation_frequency: Literal["weekly", "monthly", "quarterly"]
    min_observations_required: int
    expected_rank_ic: float
    expected_ic_decay_threshold_pct: float = 0.30
    signal_half_life_observation_periods: int | None = None
    kill_rule_params: dict[str, Any] = Field(default_factory=lambda: dict(DEFAULT_KILL_RULE_PARAMS))
    status: Literal["candidate", "paper_tracking", "promoted", "decayed", "killed", "retired"] = "paper_tracking"


class ForwardObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "2.1.0"
    observation_id: str
    plan_id: str
    period_start: date
    period_end: date
    realized_rank_ic: float | None = None
    realized_return: float | None = None
    realized_turnover: float | None = None
    realized_cost_bps: float | None = None
    observation_hash: str
    previous_observation_hash: str | None = None
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


def create_forward_tracking_plan(
    *,
    plan_id: str,
    factor_id: str,
    hypothesis_id: str,
    frozen_factor_definition_hash: str,
    expected_rank_ic: float,
    observation_frequency: Literal["weekly", "monthly", "quarterly"] = "weekly",
    min_observations_required: int | None = None,
    signal_half_life_observation_periods: int | None = None,
    kill_rule_params: dict[str, Any] | None = None,
) -> ForwardTrackingPlan:
    if not frozen_factor_definition_hash:
        raise ValueError("frozen_factor_definition_hash is required")
    kill_rule_params = dict(kill_rule_params or DEFAULT_KILL_RULE_PARAMS)
    minimum = 12
    if signal_half_life_observation_periods is not None:
        minimum = max(minimum, ceil(2 * signal_half_life_observation_periods))
    min_required = max(min_observations_required or minimum, minimum)
    frozen_config_hash = _forward_config_hash(
        frozen_factor_definition_hash=frozen_factor_definition_hash,
        observation_frequency=observation_frequency,
        min_observations_required=min_required,
        expected_rank_ic=expected_rank_ic,
        signal_half_life_observation_periods=signal_half_life_observation_periods,
        kill_rule_params=kill_rule_params,
    )
    return ForwardTrackingPlan(
        plan_id=plan_id,
        factor_id=factor_id,
        hypothesis_id=hypothesis_id,
        accepted_at=datetime.now(timezone.utc),
        frozen_factor_definition_hash=frozen_factor_definition_hash,
        frozen_config_hash=frozen_config_hash,
        observation_frequency=observation_frequency,
        min_observations_required=min_required,
        expected_rank_ic=expected_rank_ic,
        signal_half_life_observation_periods=signal_half_life_observation_periods,
        kill_rule_params=kill_rule_params,
    )


def assert_forward_plan_config_unchanged(
    plan: ForwardTrackingPlan,
    kill_rule_params: dict[str, Any],
) -> None:
    candidate_hash = _forward_config_hash(
        frozen_factor_definition_hash=plan.frozen_factor_definition_hash,
        observation_frequency=plan.observation_frequency,
        min_observations_required=plan.min_observations_required,
        expected_rank_ic=plan.expected_rank_ic,
        signal_half_life_observation_periods=plan.signal_half_life_observation_periods,
        kill_rule_params=kill_rule_params,
    )
    if candidate_hash != plan.frozen_config_hash:
        raise ForwardPlanConfigMutationError("forward plan kill_rule_params are frozen")


def create_forward_observation(
    *,
    observation_id: str,
    plan_id: str,
    period_start: date,
    period_end: date,
    realized_rank_ic: float | None = None,
    realized_return: float | None = None,
    realized_turnover: float | None = None,
    realized_cost_bps: float | None = None,
    previous_observation_hash: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> ForwardObservation:
    created_at = datetime.now(timezone.utc)
    payload = {
        "observation_id": observation_id,
        "plan_id": plan_id,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "realized_rank_ic": realized_rank_ic,
        "realized_return": realized_return,
        "realized_turnover": realized_turnover,
        "realized_cost_bps": realized_cost_bps,
        "previous_observation_hash": previous_observation_hash,
        "created_at": created_at.isoformat(),
        "metadata": metadata or {},
    }
    return ForwardObservation(
        observation_id=observation_id,
        plan_id=plan_id,
        period_start=period_start,
        period_end=period_end,
        realized_rank_ic=realized_rank_ic,
        realized_return=realized_return,
        realized_turnover=realized_turnover,
        realized_cost_bps=realized_cost_bps,
        previous_observation_hash=previous_observation_hash,
        observation_hash=canonical_hash(payload),
        created_at=created_at,
        metadata=metadata or {},
    )


def with_previous_hash(observation: ForwardObservation, previous_hash: str | None) -> ForwardObservation:
    return create_forward_observation(
        observation_id=observation.observation_id,
        plan_id=observation.plan_id,
        period_start=observation.period_start,
        period_end=observation.period_end,
        realized_rank_ic=observation.realized_rank_ic,
        realized_return=observation.realized_return,
        realized_turnover=observation.realized_turnover,
        realized_cost_bps=observation.realized_cost_bps,
        previous_observation_hash=previous_hash,
        metadata=observation.metadata,
    )


def _forward_config_hash(**payload: Any) -> str:
    return canonical_hash(payload)

