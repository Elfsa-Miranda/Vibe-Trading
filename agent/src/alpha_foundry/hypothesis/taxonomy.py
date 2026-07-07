"""A-share mechanism taxonomy constants."""

from __future__ import annotations


APPROVED_TRACKS = (
    "limit_liquidity_microstructure",
    "residual_price_volume_behavior",
    "pit_financial_quality_revision",
)

PRIMARY_FAMILY_BY_TRACK = {track: track for track in APPROVED_TRACKS}

LIMIT_LIQUIDITY_MECHANISMS = (
    "limit_lock",
    "failed_breakout",
    "one_word_board",
    "limit_gap",
    "liquidity_recovery",
)

PRICE_VOLUME_MECHANISMS = (
    "residual_momentum",
    "liquidity_conditioned_reversal",
    "turnover_unwind",
    "volume_price_divergence",
    "volatility_compression",
)

FINANCIAL_QUALITY_MECHANISMS = (
    "profitability_acceleration",
    "accrual_quality",
    "cashflow_confirmation",
    "quality_value",
    "investment_efficiency",
)

