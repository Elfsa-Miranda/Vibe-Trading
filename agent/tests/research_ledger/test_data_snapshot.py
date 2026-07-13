from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd

from src.research_ledger.data_snapshot import build_data_snapshot


def _panel() -> dict[str, object]:
    return {
        "close": pd.DataFrame({"AAA": [1.0, None], "BBB": [2.0, 3.0]}),
        "_meta": {
            "pit_contract_present": True,
            "survivorship_bias": False,
            "calendar": "SSE_SZSE",
            "timezone": "Asia/Shanghai",
        },
    }


def test_snapshot_is_deterministic_and_records_research_metadata() -> None:
    first = build_data_snapshot(
        _panel(), "fixture", "2024", {"provider": "fixture", "token": "sk-secret"}
    )
    second = build_data_snapshot(
        _panel(), "fixture", "2024", {"token": "sk-secret", "provider": "fixture"}
    )

    assert first.snapshot_hash == second.snapshot_hash
    assert first.source_config_hash == second.source_config_hash
    assert first.pit_contract_present is True and first.survivorship_bias is False
    assert first.row_counts == {"close": 2}
    assert first.missingness_summary["close"] == 0.25
    assert "sk-secret" not in json.dumps(first.to_dict(), allow_nan=False)


def test_import_does_not_create_files(tmp_path) -> None:
    environment = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": str(Path(__file__).resolve().parents[2]),
    }
    subprocess.run(
        [sys.executable, "-c", "import src.research_ledger"],
        cwd=tmp_path,
        env=environment,
        check=True,
    )
    assert not list(tmp_path.iterdir())
