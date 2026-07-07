from __future__ import annotations

import subprocess
import sys


def test_api_structure_gate_reports_incremental_compatible() -> None:
    result = subprocess.run(
        [sys.executable, "agent/scripts/check_api_structure.py"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == "incremental_compatible"
