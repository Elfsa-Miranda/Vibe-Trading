"""Dependence-aware uncertainty estimators for fixed-horizon evidence."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class DependenceEstimate:
    estimate: float
    standard_error: float
    effective_n: int
    method: str
    warnings: tuple[str, ...] = ()


def hac_mean(values: tuple[float, ...] | list[float], *, max_lag: int) -> DependenceEstimate:
    array = _finite_array(values)
    count = len(array)
    if count < 2 or max_lag < 0 or max_lag >= count:
        raise ValueError("invalid HAC sample or lag")
    centered = array - array.mean()
    long_run_variance = float(np.dot(centered, centered) / count)
    for lag in range(1, max_lag + 1):
        weight = 1.0 - lag / (max_lag + 1.0)
        covariance = float(np.dot(centered[lag:], centered[:-lag]) / count)
        long_run_variance += 2.0 * weight * covariance
    standard_error = math.sqrt(max(0.0, long_run_variance) / count)
    return DependenceEstimate(float(array.mean()), standard_error, count, f"hac_bartlett_lag_{max_lag}")


def nonoverlapping_mean(values: tuple[float, ...] | list[float], *, horizon: int) -> DependenceEstimate:
    array = _finite_array(values)
    if horizon < 1 or len(array) < horizon * 2:
        raise ValueError("insufficient data for non-overlapping cohorts")
    sampled = array[horizon - 1 :: horizon]
    standard_error = float(sampled.std(ddof=1) / math.sqrt(len(sampled)))
    return DependenceEstimate(float(sampled.mean()), standard_error, len(sampled), f"nonoverlap_horizon_{horizon}")


def moving_block_bootstrap_mean(
    values: tuple[float, ...] | list[float], *, block_length: int, replicates: int, seed: int,
) -> tuple[float, ...]:
    array = _finite_array(values)
    if not 1 <= block_length <= len(array) or replicates < 1:
        raise ValueError("invalid moving-block bootstrap configuration")
    starts = np.arange(0, len(array) - block_length + 1)
    blocks_needed = math.ceil(len(array) / block_length)
    rng = np.random.default_rng(seed)
    output: list[float] = []
    for _ in range(replicates):
        selected = rng.choice(starts, size=blocks_needed, replace=True)
        sample = np.concatenate([array[start : start + block_length] for start in selected])[: len(array)]
        output.append(float(sample.mean()))
    return tuple(output)


def _finite_array(values: tuple[float, ...] | list[float]) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if array.ndim != 1 or not len(array) or not np.isfinite(array).all():
        raise ValueError("dependence estimator requires a finite one-dimensional sample")
    return array


__all__ = ["DependenceEstimate", "hac_mean", "moving_block_bootstrap_mean", "nonoverlapping_mean"]
