"""Placebo/control diagnostics."""

from __future__ import annotations

from collections.abc import Iterable


def placebo_max_rank_ic(placebo_rank_ics: Iterable[float] | None) -> float | None:
    if placebo_rank_ics is None:
        return None
    values = [float(value) for value in placebo_rank_ics]
    if not values:
        return None
    return max(values, key=abs)

