from __future__ import annotations

from src.alpha_foundry.registry_compatibility import assess_registry_formula_compatibility
from src.factors.registry import Registry


class _FixtureAlpha:
    def __init__(self, formula: str) -> None:
        self.meta = {"formula_latex": formula}


class _FixtureRegistry:
    def __init__(self) -> None:
        self._items = {
            "fixture_canonical": _FixtureAlpha("rank(close)"),
            "fixture_legacy": _FixtureAlpha(r"\mathrm{rank}(close_t / close_{t-1})"),
        }

    def list(self) -> list[str]:
        return sorted(self._items)

    def get(self, alpha_id: str) -> _FixtureAlpha:
        return self._items[alpha_id]


def test_registry_formula_status_never_fabricates_ast_for_legacy_formula() -> None:
    records = assess_registry_formula_compatibility(_FixtureRegistry())
    by_id = {record.alpha_id: record for record in records}

    assert by_id["fixture_canonical"].status == "canonical_dsl"
    assert by_id["fixture_canonical"].expression_id is not None
    assert by_id["fixture_legacy"].status == "legacy_opaque"
    assert by_id["fixture_legacy"].expression_id is None
    assert by_id["fixture_legacy"].reason_code == "REGISTRY_FORMULA_NOT_CANONICAL_DSL"
    assert by_id["fixture_legacy"].legacy_formula_hash.startswith("sha256:")


def test_every_runtime_registry_entry_has_explicit_dynamic_compatibility_status() -> None:
    registry = Registry()
    records = assess_registry_formula_compatibility(registry)

    assert {record.alpha_id for record in records} == set(registry.list())
    assert all(record.status in {"canonical_dsl", "legacy_opaque"} for record in records)
    assert all(record.legacy_formula_hash.startswith("sha256:") for record in records)
