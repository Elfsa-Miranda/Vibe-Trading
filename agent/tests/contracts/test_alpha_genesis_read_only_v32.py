from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.alpha_genesis_routes import register_alpha_genesis_routes


async def _noop_auth() -> None:
    return None


def _report(report_id: str, marker: str = "prebuilt") -> dict[str, object]:
    return {
        "schema_version": "alpha_genesis_report.v1",
        "report_id": report_id,
        "candidate_id": "factor-1",
        "data_scope": "train_valid",
        "decision": "research_only",
        "data_snapshot_hash": "sha256:snapshot",
        "pit_contract_present": False,
        "survivorship_bias": None,
        "split_config": {"scope": "train_valid"},
        "tradability_metrics": {},
        "warnings": ["PIT evidence is incomplete"],
        "cap_reasons": ["RESEARCH_ONLY"],
        "limitations": ["PIT and execution limitations are reported"],
        "non_goals": ["not live trading authorization"],
        "marker": marker,
    }


def _client(root: Path) -> TestClient:
    app = FastAPI()
    register_alpha_genesis_routes(app, require_auth=_noop_auth, report_root=root)
    return TestClient(app)


def test_ags_openapi_contains_only_safe_read_methods(tmp_path: Path) -> None:
    app = FastAPI()
    register_alpha_genesis_routes(app, require_auth=_noop_auth, report_root=tmp_path)

    for methods in app.openapi()["paths"].values():
        assert set(methods).issubset({"get"})


def test_get_routes_read_prebuilt_artifacts_and_never_start_jobs(tmp_path: Path) -> None:
    (tmp_path / "report-1.json").write_text(
        json.dumps(_report("report-1")), encoding="utf-8"
    )
    before = {item.name: item.stat().st_mtime_ns for item in tmp_path.iterdir()}

    response = _client(tmp_path).get("/api/alpha-genesis/reports/report-1")

    assert response.status_code == 200
    assert response.json()["marker"] == "prebuilt"
    assert {item.name: item.stat().st_mtime_ns for item in tmp_path.iterdir()} == before


def test_report_root_is_frozen_when_routes_are_registered(
    tmp_path: Path, monkeypatch
) -> None:  # noqa: ANN001
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "frozen.json").write_text(
        json.dumps(_report("frozen", "first")), encoding="utf-8"
    )
    (second / "frozen.json").write_text(
        json.dumps(_report("frozen", "second")), encoding="utf-8"
    )
    monkeypatch.setenv("VIBE_TRADING_ALPHA_GENESIS_REPORT_DIR", str(first))
    app = FastAPI()
    register_alpha_genesis_routes(app, require_auth=_noop_auth)
    monkeypatch.setenv("VIBE_TRADING_ALPHA_GENESIS_REPORT_DIR", str(second))

    assert TestClient(app).get("/api/alpha-genesis/reports/frozen").json()["marker"] == "first"


def test_write_methods_do_not_create_or_change_artifacts(tmp_path: Path) -> None:
    client = _client(tmp_path)
    for method in ("post", "put", "patch", "delete"):
        assert getattr(client, method)("/api/alpha-genesis/reports/nope").status_code in {
            404,
            405,
        }
    assert list(tmp_path.iterdir()) == []
