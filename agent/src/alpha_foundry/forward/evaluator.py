"""Forward tracking evaluator wrapper."""

from __future__ import annotations

from src.alpha_foundry.forward.kill_rules import ForwardStatusEvaluation, evaluate_forward_status
from src.alpha_foundry.forward.model import ForwardObservation, ForwardTrackingPlan


def evaluate_plan(
    plan: ForwardTrackingPlan,
    observations: list[ForwardObservation],
) -> ForwardStatusEvaluation:
    return evaluate_forward_status(plan, observations)

