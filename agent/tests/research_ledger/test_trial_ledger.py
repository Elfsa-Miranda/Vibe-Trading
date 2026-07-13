from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.research_ledger.trial_ledger import (
    TrialLedgerAppendError,
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
    with pytest.raises(TrialLedgerAppendError):
        ledger.append(_entry("trial-success"))


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
    with sqlite3.connect(db_path) as conn:
        payload = conn.execute("SELECT payload FROM trial_entries").fetchone()[0]
    assert "private-secret" not in payload and "hidden-token" not in payload
    assert r"C:\\Users\\private" not in payload
    assert "NaN" not in payload and "Infinity" not in payload
    assert stored.metrics_summary["nan"] is None and stored.metrics_summary["inf"] is None

    with sqlite3.connect(db_path) as conn:
        raw = json.loads(payload)
        raw["metrics_summary"]["rank_ic"] = 0.99
        conn.execute("UPDATE trial_entries SET payload = ?", (json.dumps(raw),))
    assert not ledger.verify_hash_chain()


@pytest.mark.parametrize("column", ["entry_hash", "previous_entry_hash"])
def test_verification_checks_database_columns(tmp_path: Path, column: str) -> None:
    db_path = tmp_path / "ledger.sqlite"
    ledger = TrialLedger(db_path)
    ledger.append(_entry("one"))
    ledger.append(_entry("two"))
    with sqlite3.connect(db_path) as conn:
        conn.execute(f"UPDATE trial_entries SET {column} = 'sha256:forged' WHERE trial_id = 'two'")
    assert not ledger.verify_hash_chain()


def test_concurrent_appends_preserve_all_records_and_chain(tmp_path: Path) -> None:
    ledger = TrialLedger(tmp_path / "ledger.sqlite")
    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(lambda index: ledger.append(_entry(f"concurrent-{index}")), range(24)))
    assert len(ledger.query()) == 24
    assert ledger.verify_hash_chain()


def test_nonretryable_operational_error_does_not_sleep(tmp_path: Path, monkeypatch) -> None:
    ledger = TrialLedger(tmp_path / "ledger.sqlite")
    attempts: list[float] = []

    def fail_connect():
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(ledger, "_connect", fail_connect)
    monkeypatch.setattr("src.research_ledger.trial_ledger.time.sleep", attempts.append)
    with pytest.raises(TrialLedgerAppendError, match="disk I/O error"):
        ledger.append(_entry("io-error"))
    assert not attempts
