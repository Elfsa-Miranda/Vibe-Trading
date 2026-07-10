"""Frozen, deterministic multiple-testing adjustments."""

from __future__ import annotations

import math
from typing import Literal, Sequence

MultiplicityMethod = Literal["holm", "bh", "by"]


def adjust(pvalues: Sequence[float], method: MultiplicityMethod) -> list[float]:
    values = [float(value) for value in pvalues]
    if not values:
        return []
    if any(not math.isfinite(value) or not 0 <= value <= 1 for value in values):
        raise ValueError("p-values must be finite probabilities")
    count = len(values)
    order = sorted(range(count), key=lambda index: (values[index], index))
    adjusted = [0.0] * count
    if method == "holm":
        running = 0.0
        for rank, index in enumerate(order):
            running = max(running, (count - rank) * values[index])
            adjusted[index] = min(1.0, running)
        return adjusted
    if method not in {"bh", "by"}:
        raise ValueError("unsupported multiplicity method")
    dependence_factor = 1.0 if method == "bh" else sum(1.0 / index for index in range(1, count + 1))
    running = 1.0
    for rank, index in reversed(list(enumerate(order, start=1))):
        running = min(running, values[index] * count * dependence_factor / rank)
        adjusted[index] = min(1.0, running)
    return adjusted


__all__ = ["MultiplicityMethod", "adjust"]
