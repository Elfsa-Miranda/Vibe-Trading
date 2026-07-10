"""Deterministic v1 compatibility ranking score built from scorecard evidence."""

from __future__ import annotations

from src.alpha_quality.model import AlphaQualityScorecard


def _bounded_ratio(value: float | None, scale: float) -> float:
    if value is None:
        return 0.0
    return min(1.0, max(0.0, float(value) / scale))


def build_v1_compatibility_score(scorecard: AlphaQualityScorecard) -> float:
    """Rebuild the legacy within-tier score without accepting caller truth.

    This score preserves the v1 output field for migration. It is a bounded
    deterministic ranking heuristic, not calibrated confidence and not a v2
    tier-crossing decision rule.
    """

    rank_ic_mean: list[float] = []
    rank_icir: list[float] = []
    t_stats: list[float] = []
    if scorecard.predictive is not None:
        for horizon in scorecard.predictive.by_horizon.values():
            eligible = [
                summary
                for split, summary in horizon.by_split.items()
                if split in {"train", "valid"}
            ]
            for summary in eligible:
                if summary.rank_ic_mean is not None:
                    rank_ic_mean.append(float(summary.rank_ic_mean))
                if summary.rank_icir is not None:
                    rank_icir.append(float(summary.rank_icir))
                if summary.t_stat is not None:
                    t_stats.append(float(summary.t_stat))

    score = 0.0
    if rank_ic_mean:
        score += 0.30 * _bounded_ratio(max(rank_ic_mean), 0.04)
    if rank_icir:
        score += 0.25 * _bounded_ratio(max(rank_icir), 1.0)
    if t_stats:
        score += 0.20 * _bounded_ratio(max(t_stats), 3.0)
    if scorecard.coverage is not None:
        score += 0.10 * _bounded_ratio(scorecard.coverage.mean_coverage, 1.0)
    if scorecard.execution is not None and scorecard.execution.uses_execution_return:
        score += 0.15 * _bounded_ratio(scorecard.execution.return_mean, 0.01)
    return round(score, 12)


__all__ = ["build_v1_compatibility_score"]
