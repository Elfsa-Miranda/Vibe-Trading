from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_alpha_foundry_inventory_script_outputs_phase0_surface_map() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    script = repo_root / "agent" / "scripts" / "dump_alpha_foundry_inventory.py"

    completed = subprocess.run(
        [sys.executable, str(script)],
        cwd=repo_root,
        check=True,
        text=True,
        capture_output=True,
    )

    inventory = json.loads(completed.stdout)

    assert inventory["schema_version"] == "2.1.0-phase0"
    assert inventory["focus"]["primary_chain"] == "a_share_mechanism_alpha_foundry"
    assert inventory["focus"]["irr_agl_role"] == "evidence_and_gate_infrastructure"
    assert inventory["network_calls_performed"] is False

    assert inventory["factor_zoo"]["module_count"] >= 300
    assert {"academic", "alpha101", "gtja191", "qlib158"}.issubset(
        set(inventory["factor_zoo"]["families"])
    )
    assert "china_a" in inventory["backtest"]["engines"]
    assert {"baostock_loader", "tencent_loader", "tushare"}.issubset(
        set(inventory["data_loaders"])
    )
    assert "agent/src/reliability/artifacts/store.py" in inventory["irr_agl_surfaces"][
        "artifacts"
    ]

    financial_quality_gate = inventory["phase_gates"]["financial_quality"]
    assert financial_quality_gate["phase_5_gate"] == "adapter_only_without_real_available_at"
    assert financial_quality_gate["max_conclusion_without_real_available_at"] == "exploratory"
    assert financial_quality_gate["alpha_claim_allowed_without_available_at"] is False

    assert {
        "live_trading_expansion",
        "hft_order_book",
        "options_lab",
        "global_multi_asset_expansion",
    }.issubset(set(inventory["deferred_areas"]))
