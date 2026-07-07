"""Orthogonal portfolio increment demo fixture."""

from __future__ import annotations

from examples.alpha_foundry_demos.shared_fixtures.scenarios import build_orthogonal_portfolio_increment


def build_demo_output() -> dict:
    return build_orthogonal_portfolio_increment()
