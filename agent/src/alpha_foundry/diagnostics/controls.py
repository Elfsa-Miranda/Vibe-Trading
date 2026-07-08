"""Placebo/control diagnostics."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd

from src.alpha_foundry.diagnostics.ic import compute_ic_summary


def placebo_max_rank_ic(placebo_rank_ics: Iterable[float] | None) -> float | None:
    if placebo_rank_ics is None:
        return None
    values = [float(value) for value in placebo_rank_ics]
    if not values:
        return None
    return max(values, key=abs)


def permuted_label_rank_ics(
    factor_frame: pd.DataFrame,
    forward_returns: pd.DataFrame,
    *,
    return_column: str = "close_return",
    n_permutations: int = 100,
    random_seed: int = 0,
) -> list[float]:
    if n_permutations <= 0:
        raise ValueError("n_permutations must be positive")

    rng = np.random.default_rng(random_seed)
    values: list[float] = []
    for _ in range(n_permutations):
        permuted = forward_returns.copy()
        permuted[return_column] = (
            permuted.groupby("date", group_keys=False)[return_column]
            .transform(lambda series: pd.Series(rng.permutation(series.to_numpy()), index=series.index))
            .astype(float)
        )
        summary = compute_ic_summary(factor_frame, permuted, return_column=return_column)
        values.append(float(summary.rank_ic_raw or 0.0))
    return values

