from __future__ import annotations

from typing import Any

import importlib
import sys

from fastapi.testclient import TestClient
import pytest

import api_server


EXPECTED_PATHS = {
    "/research/alpha-foundry/reports/{report_id}",
    "/research/alpha-foundry/factors/{factor_id}",
    "/research/alpha-foundry/forward/{plan_id}",
    "/research/alpha-foundry/trials/{family_id}",
}


@pytest.fixture
def alpha_foundry_api_client(monkeypatch) -> TestClient:
    monkeypatch.setenv("VIBE_TRADING_ALPHA_FOUNDRY_MODE", "observe")
    monkeypatch.setenv("VIBE_TRADING_ALPHA_FOUNDRY_ENABLE_API", "1")
    module = importlib.reload(api_server)
    yield TestClient(module.app, client=("127.0.0.1", 50000))
    monkeypatch.delenv("VIBE_TRADING_ALPHA_FOUNDRY_MODE", raising=False)
    monkeypatch.delenv("VIBE_TRADING_ALPHA_FOUNDRY_ENABLE_API", raising=False)
    importlib.reload(api_server)


def test_alpha_foundry_mode_defaults_off_and_api_requires_dual_opt_in(monkeypatch) -> None:
    from src.api.alpha_foundry_routes import alpha_foundry_api_enabled, alpha_foundry_mode

    monkeypatch.delenv("VIBE_TRADING_ALPHA_FOUNDRY_MODE", raising=False)
    monkeypatch.delenv("VIBE_TRADING_ALPHA_FOUNDRY_ENABLE_API", raising=False)
    assert alpha_foundry_mode() == "off"
    assert alpha_foundry_api_enabled() is False

    monkeypatch.setenv("VIBE_TRADING_ALPHA_FOUNDRY_MODE", "warn")
    assert alpha_foundry_mode() == "warn"
    assert alpha_foundry_api_enabled() is False

    monkeypatch.setenv("VIBE_TRADING_ALPHA_FOUNDRY_ENABLE_API", "1")
    assert alpha_foundry_api_enabled() is True

    monkeypatch.setenv("VIBE_TRADING_ALPHA_FOUNDRY_MODE", "off")
    assert alpha_foundry_api_enabled() is False


def test_alpha_foundry_routes_absent_by_default(monkeypatch) -> None:
    monkeypatch.delenv("VIBE_TRADING_ALPHA_FOUNDRY_MODE", raising=False)
    monkeypatch.delenv("VIBE_TRADING_ALPHA_FOUNDRY_ENABLE_API", raising=False)
    module = importlib.reload(api_server)
    spec = TestClient(module.app, client=("127.0.0.1", 50000)).get("/openapi.json").json()

    assert not any(path.startswith("/research/alpha-foundry/") for path in spec["paths"])


def test_alpha_foundry_sensitive_integrations_not_imported_by_default(monkeypatch) -> None:
    monkeypatch.delenv("VIBE_TRADING_ALPHA_FOUNDRY_MODE", raising=False)
    monkeypatch.delenv("VIBE_TRADING_ALPHA_FOUNDRY_ENABLE_API", raising=False)
    for module_name in (
        "src.api.alpha_foundry_routes",
        "src.reliability.quant.methodology_facts",
        "src.reliability.quant.scorecard_policy",
        "src.research_card.builder",
        "src.research_card.render_markdown",
    ):
        sys.modules.pop(module_name, None)

    importlib.reload(api_server)

    assert "src.reliability.quant.methodology_facts" not in sys.modules
    assert "src.reliability.quant.scorecard_policy" not in sys.modules
    assert "src.research_card.builder" not in sys.modules
    assert "src.research_card.render_markdown" not in sys.modules


def test_alpha_foundry_openapi_snapshot_is_get_only(alpha_foundry_api_client) -> None:
    spec = alpha_foundry_api_client.get("/openapi.json").json()

    for path in EXPECTED_PATHS:
        assert path in spec["paths"]
        assert set(spec["paths"][path]) == {"get"}

    alpha_foundry_paths = {
        path: methods
        for path, methods in spec["paths"].items()
        if path.startswith("/research/alpha-foundry/")
    }
    assert set(alpha_foundry_paths) == EXPECTED_PATHS


def test_alpha_foundry_report_response_exact_match_and_secret_free(alpha_foundry_api_client) -> None:
    response = alpha_foundry_api_client.get("/research/alpha-foundry/reports/aaf-report")

    assert response.status_code == 200
    body = response.json()
    expected = {"EOD_PROXY_OVERCLAIM"}
    assert set(body["research_card"]["hard_failures"]) == expected
    assert set(body["scorecard"]["hard_failures"]) == expected
    assert set(body["api_fixture"]["hard_failures"]) == expected
    assert set(body["ui_fixture"]["hard_failures"]) == expected
    assert body["research_card"]["trial_count"] == 8
    assert body["research_card"]["factor_definition_hashes"] == ["hash-limit_queue_pressure_proxy"]
    assert "EOD proxy only" in body["research_card"]["proxy_notes"][0]
    assert_no_secret_keys(body)


def test_alpha_foundry_factor_forward_and_trial_contracts(alpha_foundry_api_client) -> None:
    client = alpha_foundry_api_client

    factor = client.get("/research/alpha-foundry/factors/limit_queue_pressure_proxy").json()
    assert factor["factor_id"] == "limit_queue_pressure_proxy"
    assert factor["factor_definition_hash"] == "hash-limit_queue_pressure_proxy"
    assert factor["return_validation"]["execution_return"] == "used_for_tradable_validation"
    assert factor["return_validation"]["close_return"] == "diagnostics_only"
    assert "Level-2" in factor["proxy_note"]

    forward = client.get("/research/alpha-foundry/forward/plan-limit-queue-pressure").json()
    assert forward["plan_id"] == "plan-limit-queue-pressure"
    assert forward["status"] == "paper_tracking"
    assert forward["frozen_config_hash"]
    assert forward["min_observations_required"] >= 12

    trials = client.get("/research/alpha-foundry/trials/limit_liquidity").json()
    assert trials["family_id"] == "limit_liquidity"
    assert trials["trial_count"] == 8
    assert trials["source"] == "TrialLedger"


def assert_no_secret_keys(payload: Any) -> None:
    forbidden = ("token", "secret", "api_key", "credential", "broker")
    if isinstance(payload, dict):
        for key, value in payload.items():
            lowered = str(key).lower()
            assert not any(item in lowered for item in forbidden), key
            assert_no_secret_keys(value)
    elif isinstance(payload, list):
        for item in payload:
            assert_no_secret_keys(item)
