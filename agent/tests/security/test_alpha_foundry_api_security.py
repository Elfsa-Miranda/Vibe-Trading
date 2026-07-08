from __future__ import annotations

import importlib

from fastapi.testclient import TestClient
import pytest

import api_server


ALPHA_FOUNDRY_PATHS = [
    "/research/alpha-foundry/reports/aaf-report",
    "/research/alpha-foundry/factors/limit_queue_pressure_proxy",
    "/research/alpha-foundry/forward/plan-limit-queue-pressure",
    "/research/alpha-foundry/trials/limit_liquidity",
]

TRAVERSAL_PAYLOADS = [
    "../../../etc/passwd",
    "..%2f..%2f..%2f.env",
    "%2e%2e/%2e%2e/secrets",
    r"C:\Windows\win.ini",
    "file:///etc/passwd",
    "local:../../.env",
]


@pytest.fixture
def alpha_foundry_api_client(monkeypatch) -> TestClient:
    monkeypatch.setenv("VIBE_TRADING_ALPHA_FOUNDRY_MODE", "observe")
    monkeypatch.setenv("VIBE_TRADING_ALPHA_FOUNDRY_ENABLE_API", "1")
    module = importlib.reload(api_server)
    yield TestClient(module.app, client=("127.0.0.1", 50000))
    monkeypatch.delenv("VIBE_TRADING_ALPHA_FOUNDRY_MODE", raising=False)
    monkeypatch.delenv("VIBE_TRADING_ALPHA_FOUNDRY_ENABLE_API", raising=False)
    importlib.reload(api_server)


def test_alpha_foundry_routes_reject_write_methods_without_state_change(alpha_foundry_api_client) -> None:
    client = alpha_foundry_api_client
    before = client.get("/research/alpha-foundry/trials/limit_liquidity").json()

    for path in ALPHA_FOUNDRY_PATHS:
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            response = client.request(method, path, json={"conclusion_level": "production_ready"})
            assert response.status_code in {404, 405}
        override = client.post(path, headers={"X-HTTP-Method-Override": "GET"})
        assert override.status_code in {404, 405}

    after = client.get("/research/alpha-foundry/trials/limit_liquidity").json()
    assert after == before


def test_alpha_foundry_path_traversal_returns_safe_not_found(alpha_foundry_api_client) -> None:
    client = alpha_foundry_api_client

    for payload in TRAVERSAL_PAYLOADS:
        response = client.get(f"/research/alpha-foundry/reports/{payload}")
        assert response.status_code in {404, 422}
        body = response.text.lower()
        assert "root:" not in body
        assert "[extensions]" not in body
        assert "traceback" not in body
        assert "secret" not in body
