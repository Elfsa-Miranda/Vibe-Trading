from __future__ import annotations

from fastapi import FastAPI

from api_server import create_app
from src.api.alpha_genesis_routes import register_alpha_genesis_routes


async def _noop_auth() -> None:
    return None


def test_alpha_genesis_api_is_get_only() -> None:
    app = FastAPI()
    register_alpha_genesis_routes(app, require_auth=_noop_auth)

    paths = app.openapi()["paths"]
    alpha_genesis_paths = {
        path: methods
        for path, methods in paths.items()
        if "alpha-genesis" in path
    }

    assert alpha_genesis_paths
    for methods in alpha_genesis_paths.values():
        assert set(methods).issubset({"get"})


_PRE_V32_ROUTE_INVENTORY = {
    ("/alpha/bench", "post"),
    ("/alpha/bench/{job_id}/stream", "get"),
    ("/alpha/compare", "post"),
    ("/alpha/compare/{job_id}/stream", "get"),
    ("/alpha/list", "get"),
    ("/alpha/{alpha_id}", "get"),
    ("/api", "get"),
    ("/channels/pairing/command", "post"),
    ("/channels/start", "post"),
    ("/channels/status", "get"),
    ("/channels/stop", "post"),
    ("/correlation", "get"),
    ("/health", "get"),
    ("/live/authorize", "post"),
    ("/live/halt", "post"),
    ("/live/resume", "post"),
    ("/live/runner/start", "post"),
    ("/live/runner/stop", "post"),
    ("/live/status", "get"),
    ("/mandate/commit", "post"),
    ("/qveris/config", "get"),
    ("/qveris/config", "put"),
    ("/qveris/status", "get"),
    ("/runs", "get"),
    ("/runs/{run_id}", "get"),
    ("/runs/{run_id}/code", "get"),
    ("/runs/{run_id}/pine", "get"),
    ("/scheduled-runs", "get"),
    ("/scheduled-runs", "post"),
    ("/scheduled-runs/{job_id}", "delete"),
    ("/sessions", "get"),
    ("/sessions", "post"),
    ("/sessions/{session_id}", "delete"),
    ("/sessions/{session_id}", "get"),
    ("/sessions/{session_id}", "patch"),
    ("/sessions/{session_id}/cancel", "post"),
    ("/sessions/{session_id}/events", "get"),
    ("/sessions/{session_id}/goal", "get"),
    ("/sessions/{session_id}/goal", "patch"),
    ("/sessions/{session_id}/goal", "post"),
    ("/sessions/{session_id}/goal/evidence", "post"),
    ("/sessions/{session_id}/goal/status", "patch"),
    ("/sessions/{session_id}/messages", "get"),
    ("/sessions/{session_id}/messages", "post"),
    ("/settings/data-sources", "get"),
    ("/settings/data-sources", "put"),
    ("/settings/llm", "get"),
    ("/settings/llm", "put"),
    ("/shadow-reports/{shadow_id}", "get"),
    ("/skills", "get"),
    ("/swarm/presets", "get"),
    ("/swarm/runs", "get"),
    ("/swarm/runs", "post"),
    ("/swarm/runs/{run_id}", "get"),
    ("/swarm/runs/{run_id}/cancel", "post"),
    ("/swarm/runs/{run_id}/events", "get"),
    ("/swarm/runs/{run_id}/retry", "post"),
    ("/system/shutdown", "post"),
    ("/upload", "post"),
}


def _route_inventory(app: FastAPI) -> set[tuple[str, str]]:
    return {
        (path, method.lower())
        for path, methods in app.openapi()["paths"].items()
        for method in methods
    }


def test_feature_off_openapi_and_route_inventory_match_pre_v32_golden() -> None:
    app = create_app(settings={})

    assert _route_inventory(app) == _PRE_V32_ROUTE_INVENTORY
    assert not any("alpha-genesis" in path for path in app.openapi()["paths"])


def test_report_routes_require_parent_and_child_flags_at_app_construction() -> None:
    child_only = create_app(settings={"VIBE_TRADING_ALPHA_REPORT_API": "1"})
    enabled = create_app(
        settings={
            "VIBE_TRADING_AGS_ENABLED": "1",
            "VIBE_TRADING_ALPHA_REPORT_API": "1",
        }
    )

    assert _route_inventory(child_only) == _PRE_V32_ROUTE_INVENTORY
    enabled_ags = {
        item for item in _route_inventory(enabled) if "alpha-genesis" in item[0]
    }
    assert enabled_ags == {
        ("/api/alpha-genesis/reports/{report_id}", "get"),
        ("/api/alpha-genesis/scorecards/{candidate_id}", "get"),
        ("/api/alpha-genesis/quality-decisions/{candidate_id}", "get"),
    }


def test_app_flag_snapshot_does_not_follow_mutated_settings() -> None:
    settings = {
        "VIBE_TRADING_AGS_ENABLED": "1",
        "VIBE_TRADING_ALPHA_REPORT_API": "1",
    }
    app = create_app(settings=settings)
    settings["VIBE_TRADING_ALPHA_REPORT_API"] = "0"

    assert app.state.ags_flags.enabled("VIBE_TRADING_ALPHA_REPORT_API")
    assert any("alpha-genesis" in path for path in app.openapi()["paths"])
