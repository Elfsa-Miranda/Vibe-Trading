from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from src.research_ledger.data_snapshot import build_data_snapshot
from src.research_ledger.hash_utils import canonical_json


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
    assert first.content_hash_algorithm == "sha256:canonical_json.v1"
    assert set(first.frame_content_hashes) == {"close"}
    assert "sk-secret" not in json.dumps(first.to_dict(), allow_nan=False)


@pytest.mark.parametrize(
    "changed_panel",
    [
        {"close": pd.DataFrame({"AAA": [1.0, None], "BBB": [2.0, 4.0]})},
        {"close": pd.DataFrame({"AAA": [1.0, None], "BBB": [2.0, 3.0]}, index=[1, 2])},
        {"close": pd.DataFrame({"CCC": [1.0, None], "BBB": [2.0, 3.0]})},
        {"close": pd.DataFrame({"AAA": pd.Series([1, None], dtype="Int64"), "BBB": [2, 3]})},
    ],
)
def test_snapshot_hash_changes_with_frame_content_or_structure(changed_panel) -> None:
    baseline = build_data_snapshot(_panel(), "fixture", "2024", {"provider": "fixture"})
    changed = build_data_snapshot(changed_panel, "fixture", "2024", {"provider": "fixture"})
    assert changed.snapshot_hash != baseline.snapshot_hash


def test_snapshot_is_independent_of_panel_dict_order() -> None:
    first = _panel()
    second = {"_meta": first["_meta"], "close": first["close"]}
    assert build_data_snapshot(first, "fixture", "2024", {}).snapshot_hash == build_data_snapshot(second, "fixture", "2024", {}).snapshot_hash


def test_canonical_json_rejects_sets_and_nonstring_keys() -> None:
    with pytest.raises(TypeError, match="sets"):
        canonical_json({"values": {2, 1}})
    with pytest.raises(TypeError, match="string"):
        canonical_json({1: "value"})
    with pytest.raises(TypeError, match="object"):
        canonical_json({"value": object()})


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
