from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.research_ledger.trial_ledger import TrialLedger, TrialLedgerEntry


def _entry(i: int) -> TrialLedgerEntry:
    return TrialLedgerEntry(
        trial_id=f"trial-{i}",
        trial_group_id="group",
        parent_trial_id=None,
        candidate_id=f"candidate-{i}",
        parent_seed_id=None,
        formula="rank(close)",
        formula_hash="sha256:formula",
        data_snapshot_hash="sha256:snapshot",
        universe_hash="sha256:universe",
        split_id="train_valid",
        data_scope="train",
        search_space_hash="sha256:space",
        objective="rank_ic",
        random_seed=i,
        n_candidates_seen_so_far=i + 1,
        status="success",
        decision="research_only",
        reason_codes=[],
        metrics_summary={"rank_ic": i / 1000.0},
        previous_entry_hash=None,
        entry_hash="",
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc).isoformat(),
    )


def test_concurrent_appends_do_not_corrupt_hash_chain(tmp_path) -> None:
    path = tmp_path / "ledger.sqlite"

    def append_one(i: int) -> str:
        ledger = TrialLedger(path)
        return ledger.append(_entry(i)).entry_hash

    with ThreadPoolExecutor(max_workers=4) as pool:
        hashes = list(pool.map(append_one, range(20)))

    ledger = TrialLedger(path)
    records = ledger.query()

    assert len(records) == 20
    assert len(set(hashes)) == 20
    assert ledger.verify_hash_chain()


def test_initial_schema_lock_uses_bounded_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_connect = TrialLedger._connect
    attempts = 0

    def flaky_connect(self: TrialLedger):  # noqa: ANN202
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise sqlite3.OperationalError("database is locked")
        return real_connect(self)

    monkeypatch.setattr(TrialLedger, "_connect", flaky_connect)

    ledger = TrialLedger(tmp_path / "retry.sqlite")

    assert attempts == 3
    assert ledger.query() == []
