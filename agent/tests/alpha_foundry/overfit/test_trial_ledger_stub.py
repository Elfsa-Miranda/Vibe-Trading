from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.alpha_foundry.overfit.trial_ledger import (
    AppendOnlyLedgerError,
    InMemoryTrialLedgerStore,
    JsonTrialLedgerStore,
    TrialLedger,
    TrialRecord,
)


def _record(
    trial_id: str,
    *,
    family_id: str = "limit_liquidity_microstructure",
    sub_family_id: str = "failed_limit_breakout_reversal",
    outcome: str = "reported",
) -> TrialRecord:
    return TrialRecord(
        trial_id=trial_id,
        family_id=family_id,
        sub_family_id=sub_family_id,
        hypothesis_id=sub_family_id,
        factor_id=sub_family_id,
        factor_definition_hash=f"factor-hash-{trial_id}",
        parameter_variant={"window": 5},
        param_hash=f"param-hash-{trial_id}",
        started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        completed_at=datetime(2026, 1, 1, 1, tzinfo=timezone.utc),
        outcome=outcome,
    )


def test_trial_ledger_appends_records_and_counts_by_family_and_sub_family() -> None:
    ledger = TrialLedger.create(
        ledger_id="ledger-limit",
        family_id="limit_liquidity_microstructure",
    )

    ledger = ledger.append(_record("trial-1"))
    ledger = ledger.append(_record("trial-2", sub_family_id="limit_lock_strength"))

    assert ledger.trial_count() == 2
    assert ledger.trial_count(family_id="limit_liquidity_microstructure") == 2
    assert ledger.trial_count(sub_family_id="failed_limit_breakout_reversal") == 1
    assert ledger.records[0].trial_id == "trial-1"
    assert ledger.ledger_hash


def test_trial_ledger_rejects_duplicate_trial_id() -> None:
    ledger = TrialLedger.create(
        ledger_id="ledger-limit",
        family_id="limit_liquidity_microstructure",
    ).append(_record("trial-1"))

    with pytest.raises(AppendOnlyLedgerError, match="duplicate trial_id"):
        ledger.append(_record("trial-1"))


def test_trial_ledger_rejects_mismatched_family() -> None:
    ledger = TrialLedger.create(
        ledger_id="ledger-limit",
        family_id="limit_liquidity_microstructure",
    )

    with pytest.raises(AppendOnlyLedgerError, match="family_id"):
        ledger.append(_record("trial-1", family_id="residual_price_volume_behavior"))


def test_in_memory_store_appends_without_mutating_previous_ledger() -> None:
    store = InMemoryTrialLedgerStore()
    empty = store.create("ledger-limit", "limit_liquidity_microstructure")
    updated = store.append("ledger-limit", _record("trial-1"))

    assert empty.trial_count() == 0
    assert updated.trial_count() == 1
    assert store.get("ledger-limit").trial_count() == 1


def test_json_store_round_trips_append_only_records(tmp_path) -> None:
    store = JsonTrialLedgerStore(tmp_path)
    store.create("ledger-limit", "limit_liquidity_microstructure")
    store.append("ledger-limit", _record("trial-1"))
    store.append("ledger-limit", _record("trial-2", sub_family_id="limit_lock_strength"))

    loaded = store.get("ledger-limit")
    assert loaded.trial_count() == 2
    assert loaded.trial_count(sub_family_id="limit_lock_strength") == 1
    assert (tmp_path / "ledger-limit.jsonl").read_text(encoding="utf-8").count("\n") == 3
