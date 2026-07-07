from __future__ import annotations

import sys
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parents[3]
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

from fixture import build_demo_output  # noqa: E402
from examples.alpha_foundry_demos.shared_fixtures.factory import run_demo_cli  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(run_demo_cli(Path(__file__).resolve().parent, build_demo_output))
