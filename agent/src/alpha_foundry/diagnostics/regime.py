"""Regime diagnostics."""

from __future__ import annotations

from collections.abc import Mapping


def negative_regime_fraction(regime_ic: Mapping[str, float] | None) -> float | None:
    if not regime_ic:
        return None
    values = list(regime_ic.values())
    return sum(1 for value in values if value < 0.0) / len(values)

