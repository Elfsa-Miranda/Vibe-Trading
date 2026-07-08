from __future__ import annotations

import json
from datetime import date

import pytest

from src.alpha_foundry.forward.model import create_forward_observation
from src.alpha_foundry.forward.store import ForwardObservationJsonlStore, ForwardStoreMutationError


def _observation(observation_id: str, *, start: date, end: date, previous_hash: str | None = None):
    return create_forward_observation(
        observation_id=observation_id,
        plan_id="plan-sec",
        period_start=start,
        period_end=end,
        realized_rank_ic=0.01,
        previous_observation_hash=previous_hash,
    )


def test_forward_store_rejects_duplicate_observation_id(tmp_path) -> None:
    store = ForwardObservationJsonlStore(tmp_path / "forward.jsonl")
    store.append(_observation("obs-1", start=date(2026, 1, 5), end=date(2026, 1, 9)))

    with pytest.raises(ForwardStoreMutationError, match="duplicate observation_id"):
        store.append(_observation("obs-1", start=date(2026, 1, 12), end=date(2026, 1, 16)))


def test_forward_store_rejects_forged_previous_hash(tmp_path) -> None:
    store = ForwardObservationJsonlStore(tmp_path / "forward.jsonl")
    store.append(_observation("obs-1", start=date(2026, 1, 5), end=date(2026, 1, 9)))

    forged = _observation(
        "obs-2",
        start=date(2026, 1, 12),
        end=date(2026, 1, 16),
        previous_hash="forged-previous-hash",
    )
    with pytest.raises(ForwardStoreMutationError, match="previous_observation_hash"):
        store.append(forged)


def test_forward_store_detects_tampered_jsonl_line(tmp_path) -> None:
    path = tmp_path / "forward.jsonl"
    store = ForwardObservationJsonlStore(path)
    store.append(_observation("obs-1", start=date(2026, 1, 5), end=date(2026, 1, 9)))

    payload = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    payload["realized_rank_ic"] = 0.99
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(ForwardStoreMutationError, match="hash mismatch"):
        store.list_observations("plan-sec")


def test_forward_store_rejects_path_traversal(tmp_path) -> None:
    with pytest.raises(ForwardStoreMutationError, match="path traversal"):
        ForwardObservationJsonlStore(tmp_path / "store" / ".." / "outside.jsonl")
