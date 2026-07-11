from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.alpha_quality.reporting import (
    ReportArtifactKind,
    ReportArtifactReader,
    ReportArtifactValidationError,
    ReportPathError,
)
from src.alpha_quality.reporting.safety import validate_report_name
from src.api.alpha_genesis_routes import register_alpha_genesis_routes


async def _noop_auth() -> None:
    return None


def _report(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "alpha_genesis_report.v1",
        "report_id": "safe",
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
        "limitations": ["inconclusive evidence remains inconclusive"],
        "non_goals": ["not live trading authorization"],
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize(
    "value",
    [
        "../secret",
        "..\\secret",
        "%2e%2e%2fsecret",
        "C:\\private",
        "\\\\server\\share",
        "\\\\?\\C:\\private",
        "\\\\.\\PhysicalDrive0",
        "report.json:secret",
        "report\uff0ejson",
        "name\x00.json",
    ],
)
def test_windows_path_safety_rejects_unc_device_ads_and_traversal(value: str) -> None:
    with pytest.raises(ReportPathError):
        validate_report_name(value)


def test_artifact_root_rejects_symlink_or_junction_escape(tmp_path: Path) -> None:
    root = tmp_path / "reports"
    root.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps(_report()), encoding="utf-8")
    link = root / "escape.json"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation is unavailable on this Windows host")

    with pytest.raises(ReportPathError):
        ReportArtifactReader(root).read("escape", ReportArtifactKind.REPORT)


@pytest.mark.parametrize(
    "body",
    [
        '{"schema_version":"alpha_genesis_report.v999"}',
        '{"schema_version":"alpha_genesis_report.v1","value":NaN}',
        '{"schema_version":"alpha_genesis_report.v1","value":Infinity}',
        '{"schema_version":"alpha_genesis_report.v1","x":1,"x":2}',
    ],
)
def test_report_schema_rejects_nan_infinity_duplicates_and_unknown_versions(
    tmp_path: Path, body: str
) -> None:
    (tmp_path / "bad.json").write_text(body, encoding="utf-8")
    with pytest.raises(ReportArtifactValidationError):
        ReportArtifactReader(tmp_path).read("bad", ReportArtifactKind.REPORT)


def test_reports_redact_secrets_accounts_paths_and_query_values(tmp_path: Path) -> None:
    private_path = str(tmp_path / "private" / "artifact.json")
    payload = _report(
        metadata={
            "api_key": "sk-secret-value",
            "account_id": "private-account-42",
            "artifact_path": private_path,
            "diagnostic": "Authorization: Bearer bearer-secret",
        }
    )
    (tmp_path / "safe.json").write_text(json.dumps(payload), encoding="utf-8")
    app = FastAPI()
    register_alpha_genesis_routes(app, require_auth=_noop_auth, report_root=tmp_path)

    response = TestClient(app).get(
        "/api/alpha-genesis/reports/safe?token=query-secret"
    )

    assert response.status_code == 200
    rendered = response.text
    for secret in (
        "sk-secret-value",
        "private-account-42",
        private_path,
        "bearer-secret",
        "query-secret",
    ):
        assert secret not in rendered


def test_html_and_markdown_fields_are_safely_served_as_sandboxed_json(tmp_path: Path) -> None:
    (tmp_path / "safe.json").write_text(
        json.dumps(_report(limitations=["<script>alert(1)</script>", "[x](javascript:alert(1))"])),
        encoding="utf-8",
    )
    app = FastAPI()
    register_alpha_genesis_routes(app, require_auth=_noop_auth, report_root=tmp_path)

    response = TestClient(app).get("/api/alpha-genesis/reports/safe")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-security-policy"] == "default-src 'none'; sandbox"


def test_live_or_missing_research_boundary_report_fails_closed(tmp_path: Path) -> None:
    (tmp_path / "unsafe.json").write_text(
        json.dumps(_report(decision="production_ready")), encoding="utf-8"
    )
    (tmp_path / "missing.json").write_text(
        json.dumps({"schema_version": "alpha_genesis_report.v2"}), encoding="utf-8"
    )
    reader = ReportArtifactReader(tmp_path)

    with pytest.raises(ReportArtifactValidationError):
        reader.read("unsafe", ReportArtifactKind.REPORT)
    with pytest.raises(ReportArtifactValidationError):
        reader.read("missing", ReportArtifactKind.REPORT)


def test_legacy_v1_missing_boundaries_is_capped_and_annotated(tmp_path: Path) -> None:
    (tmp_path / "legacy.json").write_text(
        json.dumps({"schema_version": "alpha_genesis_report.v1", "report_id": "legacy"}),
        encoding="utf-8",
    )

    payload = ReportArtifactReader(tmp_path).read("legacy", ReportArtifactKind.REPORT)

    assert payload["decision"] == "research_only"
    assert payload["cap_reasons"] == ["RESEARCH_ONLY"]
    assert payload["report_safety"]["legacy_boundary_incomplete"] is True


def test_nested_v2_decision_cannot_smuggle_live_label(tmp_path: Path) -> None:
    (tmp_path / "factor.decision.json").write_text(
        json.dumps(
            {
                "schema_version": "quality_decision_artifact.v2",
                "decision": {"decision": "approved_to_trade"},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ReportArtifactValidationError):
        ReportArtifactReader(tmp_path).read("factor", ReportArtifactKind.DECISION)


def test_report_reader_enforces_bounded_size_and_depth(tmp_path: Path) -> None:
    (tmp_path / "large.json").write_text("{}" * 100, encoding="utf-8")
    with pytest.raises(ReportArtifactValidationError):
        ReportArtifactReader(tmp_path, max_bytes=16).read(
            "large", ReportArtifactKind.REPORT
        )

    nested: object = "leaf"
    for _ in range(40):
        nested = {"x": nested}
    (tmp_path / "deep.json").write_text(json.dumps(nested), encoding="utf-8")
    with pytest.raises(ReportArtifactValidationError):
        ReportArtifactReader(tmp_path).read("deep", ReportArtifactKind.REPORT)
