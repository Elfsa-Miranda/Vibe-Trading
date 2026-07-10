"""Provenance-complete dynamic registry bootstrap for Factor DAG roots."""

from __future__ import annotations

from typing import Protocol

from src.alpha_foundry.dsl.grammar import DEFAULT_GRAMMAR, GrammarDefinition
from src.alpha_foundry.registry_compatibility import assess_registry_formula_compatibility
from src.research_ledger.hash_utils import canonical_json_hash


class RegistryBootstrapSource(Protocol):
    def list(self) -> list[str]: ...
    def get(self, alpha_id: str): ...


def build_registry_bootstrap_payload(
    registry: RegistryBootstrapSource,
    *,
    grammar: GrammarDefinition = DEFAULT_GRAMMAR,
) -> dict[str, object]:
    """Produce a closed event payload from the runtime registry, never a count."""
    compatibility = assess_registry_formula_compatibility(registry)
    roots = [
        {
            "alpha_id": item.alpha_id,
            "status": item.status,
            "expression_id": item.expression_id,
            "legacy_formula_hash": item.legacy_formula_hash,
        }
        for item in compatibility
    ]
    sources: dict[str, str] = {}
    get_source = getattr(registry, "get_source", None)
    unavailable: list[str] = []
    for alpha_id in sorted(registry.list()):
        if callable(get_source):
            try:
                sources[alpha_id] = canonical_json_hash({"source": get_source(alpha_id)})
            except (OSError, ValueError, KeyError):
                unavailable.append(alpha_id)
        else:
            unavailable.append(alpha_id)
    registry_snapshot_hash = canonical_json_hash({"roots": roots})
    registry_code_hash = canonical_json_hash(
        {"source_hashes": sources, "source_unavailable": unavailable}
    )
    snapshot_id = "registry-" + registry_snapshot_hash.removeprefix("sha256:")[:16]
    return {
        "snapshot_id": snapshot_id,
        "registry_snapshot_hash": registry_snapshot_hash,
        "registry_code_hash": registry_code_hash,
        "grammar_hash": grammar.content_hash,
        "roots": roots,
    }


__all__ = ["RegistryBootstrapSource", "build_registry_bootstrap_payload"]
