"""IC decay diagnostics."""

from __future__ import annotations

from collections.abc import Mapping


def estimate_decay_half_life_days(horizon_rank_ics: Mapping[int, float] | None) -> float | None:
    if not horizon_rank_ics:
        return None
    ordered = sorted((int(h), abs(float(ic))) for h, ic in horizon_rank_ics.items())
    if not ordered:
        return None
    first_horizon, first_ic = ordered[0]
    if first_ic <= 0:
        return None
    threshold = first_ic / 2.0
    for horizon, value in ordered:
        if horizon == first_horizon:
            continue
        if value <= threshold:
            return float(horizon)
    return None

