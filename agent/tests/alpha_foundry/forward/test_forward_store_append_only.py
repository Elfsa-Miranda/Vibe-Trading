from __future__ import annotations

from datetime import date

import pytest

from src.alpha_foundry.forward.model import create_forward_observation
from src.alpha_foundry.forward.store import ForwardObservationJsonlStore, ForwardStoreMutationError


def test_forward_store_appends_jsonl_and_chains_hashes(tmp_path) -> None:
    store = ForwardObservationJsonlStore(tmp_path / "forward.jsonl")
    first = create_forward_observation(
        observation_id="obs-1",
        plan_id="plan-1",
        period_start=date(2026, 1, 5),
        period_end=date(2026, 1, 9),
        realized_rank_ic=0.02,
    )
    second = create_forward_observation(
        observation_id="obs-2",
        plan_id="plan-1",
        period_start=date(2026, 1, 12),
        period_end=date(2026, 1, 16),
        realized_rank_ic=0.03,
    )

    first = store.append(first)
    second = store.append(second)
    observations = store.list_observations("plan-1")

    assert len(observations) == 2
    assert observations[0].previous_observation_hash is None
    assert observations[1].previous_observation_hash == observations[0].observation_hash
    assert second.observation_hash == observations[1].observation_hash


def test_forward_store_rejects_update_delete_and_out_of_order_append(tmp_path) -> None:
    store = ForwardObservationJsonlStore(tmp_path / "forward.jsonl")
    first = store.append(
        create_forward_observation(
            observation_id="obs-1",
            plan_id="plan-1",
            period_start=date(2026, 1, 12),
            period_end=date(2026, 1, 16),
            realized_rank_ic=0.02,
        )
    )
    out_of_order = create_forward_observation(
        observation_id="obs-0",
        plan_id="plan-1",
        period_start=date(2026, 1, 5),
        period_end=date(2026, 1, 9),
        realized_rank_ic=0.01,
    )

    with pytest.raises(ForwardStoreMutationError):
        store.update(first)
    with pytest.raises(ForwardStoreMutationError):
        store.delete("obs-1")
    with pytest.raises(ForwardStoreMutationError):
        store.append(out_of_order)

