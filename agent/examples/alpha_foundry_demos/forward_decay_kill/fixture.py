"""Forward decay kill demo fixture."""

from __future__ import annotations

from examples.alpha_foundry_demos.shared_fixtures.scenarios import build_forward_decay_kill


def build_demo_output() -> dict:
    return build_forward_decay_kill()
