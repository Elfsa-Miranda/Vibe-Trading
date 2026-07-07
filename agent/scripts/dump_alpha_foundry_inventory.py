"""Dump the Phase 0 Alpha Foundry inventory as deterministic JSON.

This script is intentionally read-only. It inspects tracked repository files
with ``git ls-files`` and never imports market-data loaders, broker adapters,
or runtime tool registries.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _tracked_files(repo_root: Path) -> list[str]:
    completed = subprocess.run(
        ["git", "ls-files"],
        cwd=repo_root,
        check=True,
        text=True,
        capture_output=True,
    )
    return [line.strip().replace("\\", "/") for line in completed.stdout.splitlines() if line.strip()]


def _stems_under(files: list[str], prefix: str) -> list[str]:
    out: list[str] = []
    for path in files:
        if not path.startswith(prefix) or not path.endswith(".py"):
            continue
        stem = Path(path).stem
        if stem.startswith("__"):
            continue
        out.append(stem)
    return sorted(set(out))


def _factor_zoo(files: list[str]) -> dict[str, Any]:
    modules: list[str] = []
    families: set[str] = set()
    for path in files:
        parts = path.split("/")
        if len(parts) != 6:
            continue
        if parts[:4] != ["agent", "src", "factors", "zoo"]:
            continue
        if not path.endswith(".py") or parts[-1].startswith("__"):
            continue
        families.add(parts[4])
        modules.append(path)
    return {
        "families": sorted(families),
        "module_count": len(modules),
        "sample_modules": modules[:12],
    }


def build_inventory() -> dict[str, Any]:
    repo_root = _repo_root()
    files = _tracked_files(repo_root)

    factor_tests = [p for p in files if p.startswith("agent/tests/factors/") and p.endswith(".py")]
    backtest_tests = [
        p
        for p in files
        if p.startswith("agent/tests/")
        and p.endswith(".py")
        and ("backtest" in p or "china_a" in p or "loader" in p)
    ]

    inventory: dict[str, Any] = {
        "schema_version": "2.1.0-phase0",
        "network_calls_performed": False,
        "focus": {
            "primary_chain": "a_share_mechanism_alpha_foundry",
            "irr_agl_role": "evidence_and_gate_infrastructure",
            "non_goal": "horizontal_agent_expansion",
        },
        "factor_zoo": _factor_zoo(files),
        "backtest": {
            "engines": _stems_under(files, "agent/backtest/engines/"),
            "optimizers": _stems_under(files, "agent/backtest/optimizers/"),
            "tests": sorted(backtest_tests),
        },
        "data_loaders": _stems_under(files, "agent/backtest/loaders/"),
        "tools": _stems_under(files, "agent/src/tools/"),
        "api_surfaces": _stems_under(files, "agent/src/api/"),
        "irr_agl_surfaces": {
            "artifacts": sorted(
                p for p in files if p.startswith("agent/src/reliability/artifacts/") and p.endswith(".py")
            ),
            "reliability_core": sorted(
                p
                for p in files
                if p.startswith("agent/src/reliability/")
                and p.endswith(".py")
                and "/artifacts/" not in p
            ),
            "research_card": sorted(p for p in files if p.startswith("agent/src/research_card/")),
            "governance": sorted(p for p in files if p.startswith("agent/src/governance/")),
        },
        "current_test_coverage_surfaces": {
            "factor_tests": sorted(factor_tests),
            "factor_test_count": len(factor_tests),
            "backtest_loader_engine_tests": sorted(backtest_tests),
            "backtest_loader_engine_test_count": len(backtest_tests),
            "reliability_tests": sorted(
                p for p in files if p.startswith("agent/tests/reliability/") and p.endswith(".py")
            ),
        },
        "alpha_tracks": {
            "in_scope": [
                "limit_liquidity_microstructure",
                "residual_price_volume_behavior",
                "pit_financial_quality_revision",
            ],
            "phase0_priority": [
                "limit_liquidity_microstructure",
                "residual_price_volume_behavior",
            ],
            "data_gated": ["pit_financial_quality_revision"],
        },
        "phase_gates": {
            "financial_quality": {
                "available_at_status": "not_proven_available_in_current_tracked_code",
                "announcement_time_proxy": "allowed_only_if_documented_with_one_trading_day_lag",
                "phase_5_gate": "adapter_only_without_real_available_at",
                "max_conclusion_without_real_available_at": "exploratory",
                "alpha_claim_allowed_without_available_at": False,
            }
        },
        "deferred_areas": [
            "live_trading_expansion",
            "hft_order_book",
            "options_lab",
            "global_multi_asset_expansion",
        ],
    }
    return inventory


def main() -> None:
    print(json.dumps(build_inventory(), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
