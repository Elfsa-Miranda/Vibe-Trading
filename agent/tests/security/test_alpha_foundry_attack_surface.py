from __future__ import annotations

from pathlib import Path

from src.alpha_foundry.factors.limit_liquidity import (
    compute_limit_liquidity_factor,
    get_limit_liquidity_factor_metadata,
)
from src.alpha_foundry.forward.store import ForwardObservationJsonlStore
from tests.alpha_foundry.fixtures.factory import make_limit_liquidity_factor_input_frame


def test_forward_store_has_no_public_update_or_delete_mutation_api() -> None:
    assert "update" not in ForwardObservationJsonlStore.__dict__
    assert "delete" not in ForwardObservationJsonlStore.__dict__


def test_forward_store_normalizes_relative_paths_before_use(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    store = ForwardObservationJsonlStore(Path("forward.jsonl"))

    assert store.path.is_absolute()
    assert store.path == (tmp_path / "forward.jsonl").resolve(strict=False)


def test_queue_pressure_proxy_without_level2_is_fixture_only_exploratory() -> None:
    metadata = get_limit_liquidity_factor_metadata(
        "limit_queue_pressure_proxy",
        level2_available=False,
    )
    output = compute_limit_liquidity_factor(
        make_limit_liquidity_factor_input_frame(),
        "limit_queue_pressure_proxy",
        level2_available=False,
    )

    assert metadata.exploratory_only is True
    assert metadata.can_claim_level2_queue_alpha is False
    assert metadata.proxy_note and "Level-2" in metadata.proxy_note
    assert metadata.data_availability_policy == "fixture_only"
    assert set(output["data_availability_policy"]) == {"fixture_only"}
