"""Deterministic forward tracking kill/promote rules."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.alpha_foundry.forward.model import ForwardObservation, ForwardTrackingPlan


class ForwardStatusEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "2.1.0"
    plan_id: str
    status: Literal["paper_tracking", "promoted", "decayed", "killed"]
    reasons: list[str] = Field(default_factory=list)


def evaluate_forward_status(
    plan: ForwardTrackingPlan,
    observations: list[ForwardObservation],
) -> ForwardStatusEvaluation:
    params = plan.kill_rule_params
    consecutive_negative_n = int(params.get("consecutive_negative_ic_n", 3))
    ratio_min = float(params.get("realized_vs_expected_ratio_min", 0.30))

    realized_rank_ics = [obs.realized_rank_ic for obs in observations if obs.realized_rank_ic is not None]
    if _last_n_negative(realized_rank_ics, consecutive_negative_n):
        return ForwardStatusEvaluation(plan_id=plan.plan_id, status="killed", reasons=["consecutive_negative_ic"])

    if len(observations) < plan.min_observations_required:
        return ForwardStatusEvaluation(plan_id=plan.plan_id, status="paper_tracking", reasons=["min_observations_not_met"])

    mean_ic = sum(realized_rank_ics) / len(realized_rank_ics) if realized_rank_ics else 0.0
    if plan.expected_rank_ic > 0 and mean_ic / plan.expected_rank_ic < ratio_min:
        return ForwardStatusEvaluation(plan_id=plan.plan_id, status="decayed", reasons=["realized_vs_expected_ic_decay"])

    return ForwardStatusEvaluation(plan_id=plan.plan_id, status="promoted", reasons=["min_observations_met"])


def _last_n_negative(values: list[float], n: int) -> bool:
    if len(values) < n:
        return False
    return all(value < 0 for value in values[-n:])

