"""Public alpha crowding trap demo fixture."""

from __future__ import annotations

from examples.alpha_foundry_demos.shared_fixtures.scenarios import build_public_alpha_crowding_trap


def build_demo_output() -> dict:
    return build_public_alpha_crowding_trap()
