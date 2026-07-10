"""Deterministic equivalence testing for frozen fixed-horizon contracts."""

from __future__ import annotations

import math
from dataclasses import dataclass

from scipy.stats import norm


@dataclass(frozen=True)
class EquivalenceResult:
    estimate: float
    standard_error: float
    margin: float
    alpha: float
    lower_p_value: float
    upper_p_value: float
    confidence_interval: tuple[float, float]
    equivalent: bool
    inconclusive: bool
    reason_codes: tuple[str, ...]


def tost_from_summary(
    *,
    estimate: float,
    standard_error: float,
    margin: float,
    alpha: float,
    effective_n: int,
    minimum_effective_n: int,
) -> EquivalenceResult:
    """Run TOST for H0: effect <= -margin OR effect >= margin.

    The two one-sided components form one intersection-union family member.
    Both must reject at the allocated alpha. A low effective sample or invalid
    uncertainty produces an explicit inconclusive result.
    """
    values = (estimate, standard_error, margin, alpha)
    if not all(math.isfinite(float(value)) for value in values):
        raise ValueError("TOST inputs must be finite")
    if margin <= 0 or not 0 < alpha < 0.5:
        raise ValueError("TOST margin and alpha are invalid")
    if effective_n < 0 or minimum_effective_n < 1:
        raise ValueError("effective sample sizes are invalid")
    if standard_error <= 0 or effective_n < minimum_effective_n:
        return EquivalenceResult(
            estimate, standard_error, margin, alpha, 1.0, 1.0,
            (estimate, estimate), False, True,
            ("LOW_POWER",) if effective_n < minimum_effective_n else ("INVALID_UNCERTAINTY",),
        )
    lower_z = (estimate + margin) / standard_error
    upper_z = (estimate - margin) / standard_error
    lower_p = float(norm.sf(lower_z))
    upper_p = float(norm.cdf(upper_z))
    critical = float(norm.ppf(1.0 - alpha))
    interval = (estimate - critical * standard_error, estimate + critical * standard_error)
    equivalent = lower_p <= alpha and upper_p <= alpha
    return EquivalenceResult(
        estimate, standard_error, margin, alpha, lower_p, upper_p, interval,
        equivalent, not equivalent, () if equivalent else ("EQUIVALENCE_NOT_ESTABLISHED",),
    )


def tost(
    *, lower_p: float, upper_p: float, alpha: float,
    effective_n: int, min_effective_n: int,
) -> EquivalenceResult:
    """Compatibility helper when preregistered one-sided p-values are supplied."""
    if not all(math.isfinite(value) and 0 <= value <= 1 for value in (lower_p, upper_p)):
        raise ValueError("TOST p-values must be finite probabilities")
    if not 0 < alpha < 0.5:
        raise ValueError("TOST alpha is invalid")
    low_power = effective_n < min_effective_n
    equivalent = not low_power and lower_p <= alpha and upper_p <= alpha
    return EquivalenceResult(
        0.0, 0.0, 0.0, alpha, lower_p, upper_p,
        (0.0, 0.0), equivalent, not equivalent,
        ("LOW_POWER",) if low_power else (() if equivalent else ("EQUIVALENCE_NOT_ESTABLISHED",)),
    )


__all__ = ["EquivalenceResult", "tost", "tost_from_summary"]
