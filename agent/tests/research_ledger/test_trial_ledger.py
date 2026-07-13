from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.research_ledger.trial_ledger import (
    TrialLedger,
    TrialLedgerEntry,
    TrialLedgerMutationError,
)


def _entry(trial_id: str, status: str = "success", **overrides: object) -> TrialLedgerEntry:
    values: dict[str, object] = {
        "trial_id": trial_id,
        "trial_group_id": "fixture-group",
        "parent_trial_id": None,
        "candidate_id": f"candidate-{trial_id}",
        "parent_seed_id": None,
        "formula": "rank(close)",
        "formula_hash": "sha256:formula",
        "data_snapshot_hash": "sha256:snapshot",
        "universe_hash": "sha256:universe",
        "split_id": "train-valid",
        "data_scope": "train",
        "search_space_hash": "sha256:space",
        "objective": "rank_ic",
        "random_seed": 1,
        "n_candidates_seen_so_far": 1,
        "status": status,
        "decision": "research_only",
        "reason_codes": [],
        "metrics_summary": {"rank_ic": 0.02},
        "previous_entry_hash": None,
        "entry_hash": "",
        "created_at": datetime(2024, 1, 1, tzinfo=timezone.utc).isoformat(),
    }
    values.update(overrides)
    return TrialLedgerEntry(**values)  # type: ignore[arg-type]


def test_append_only_hash_chain_and_terminal_records(tmp_path: Path) -> None:
    ledger = TrialLedger(tmp_path / "ledger.sqlite")
    records = [ledger.append(_entry(f"trial-{status}", status)) for status in ("success", "reject", "skip", "error")]

    assert [record.status for record in ledger.query()] == ["success", "reject", "skip", "error"]
    assert records[0].previous_entry_hash is None
    assert records[1].previous_entry_hash == records[0].entry_hash
    assert ledger.verify_hash_chain()
    with pytest.raises(TrialLedgerMutationError):
        ledger.update("trial-success")
    with pytest.raises(TrialLedgerMutationError):
        ledger.delete("trial-success")


def test_tampering_and_sensitive_or_nonfinite_payloads_are_safe(tmp_path: Path) -> None:
    db_path = tmp_path / "ledger.sqlite"
    ledger = TrialLedger(db_path)
    stored = ledger.append(
        _entry(
            "trial-safe",
            parameter_variant={"api_key": "sk-private-secret", "path": r"C:\\Users\\private\\data"},
            metrics_summary={"token": "hidden-token", "nan": float("nan"), "inf": float("inf")},
        )
    )
    payload = json.dumps(stored.to_dict(), allow_nan=False)
    assert "private-secret" not in payload and "hidden-token" not in payload
    assert r"C:\\Users\\private" not in payload
    assert stored.metrics_summary["nan"] is None and stored.metrics_summary["inf"] is None

    with sqlite3.connect(db_path) as conn:
        raw = json.loads(conn.execute("SELECT payload FROM trial_entries").fetchone()[0])
        raw["metrics_summary"]["rank_ic"] = 0.99
        conn.execute("UPDATE trial_entries SET payload = ?", (json.dumps(raw),))
    assert not ledger.verify_hash_chain()
