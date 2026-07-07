"""Portfolio exposure helpers."""

from __future__ import annotations


def summarize_sector_weights(weights: dict[str, float], sectors: dict[str, str]) -> dict[str, float]:
    summary: dict[str, float] = {}
    for symbol, weight in weights.items():
        sector = sectors.get(symbol, "unknown")
        summary[sector] = summary.get(sector, 0.0) + float(weight)
    return summary

