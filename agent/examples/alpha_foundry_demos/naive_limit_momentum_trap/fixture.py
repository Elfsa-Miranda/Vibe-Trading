"""Naive limit momentum trap demo fixture."""

from __future__ import annotations

from examples.alpha_foundry_demos.shared_fixtures.scenarios import build_naive_limit_momentum_trap


def build_demo_output() -> dict:
    return build_naive_limit_momentum_trap()
