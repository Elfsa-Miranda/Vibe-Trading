"""Provenance-complete dynamic registry bootstrap for Factor DAG roots."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from src.alpha_foundry.dsl.grammar import DEFAULT_GRAMMAR, GrammarDefinition
from src.alpha_foundry.dsl.identity import build_expression_identity
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
    compatibility = assess_registry_formula_compatibility(registry, grammar=grammar)
    roots: list[dict[str, object]] = []
    get_source = getattr(registry, "get_source", None)
    by_id = {item.alpha_id: item for item in compatibility}
    for alpha_id in sorted(by_id):
        source_hash: str | None = None
        source_status = "unavailable"
        source_reason: str | None = "REGISTRY_SOURCE_API_UNAVAILABLE"
        if callable(get_source):
            try:
                source_hash = canonical_json_hash({"source": get_source(alpha_id)})
                source_status = "available"
                source_reason = None
            except (OSError, TypeError, ValueError, KeyError):
                source_reason = "REGISTRY_SOURCE_READ_FAILED"
        item = by_id[alpha_id]
        roots.append(
            {
                "alpha_id": item.alpha_id,
                "status": item.status,
                "expression_id": item.expression_id,
                "canonical_formula": item.canonical_formula,
                "legacy_formula_hash": item.legacy_formula_hash,
                "source_hash": source_hash,
                "source_status": source_status,
                "source_reason": source_reason,
            }
        )
    registry_snapshot_hash = canonical_json_hash(
        {
            "grammar_version": grammar.semantic_version,
            "grammar_hash": grammar.content_hash,
            "roots": roots,
        }
    )
    registry_code_hash = canonical_json_hash({"sources": _source_evidence(roots)})
    snapshot_id = "registry-" + registry_snapshot_hash.removeprefix("sha256:")[:16]
    return {
        "snapshot_id": snapshot_id,
        "registry_snapshot_hash": registry_snapshot_hash,
        "registry_code_hash": registry_code_hash,
        "grammar_version": grammar.semantic_version,
        "grammar_hash": grammar.content_hash,
        "grammar_definition": grammar.to_dict(),
        "roots": roots,
    }


def validate_registry_bootstrap_payload(payload: Mapping[str, object]) -> None:
    expected = {
        "snapshot_id", "registry_snapshot_hash", "registry_code_hash",
        "grammar_version", "grammar_hash", "grammar_definition", "roots",
    }
    if set(payload) != expected or not isinstance(payload["grammar_definition"], Mapping):
        raise ValueError("registry bootstrap v2 payload is not closed")
    grammar = GrammarDefinition.from_dict(payload["grammar_definition"])
    if (
        grammar.semantic_version != payload["grammar_version"]
        or grammar.content_hash != payload["grammar_hash"]
    ):
        raise ValueError("registry bootstrap grammar identity mismatch")
    roots = payload["roots"]
    if not isinstance(roots, (list, tuple)):
        raise ValueError("registry bootstrap roots are malformed")
    normalized = [dict(root) for root in roots if isinstance(root, Mapping)]
    alpha_ids = [root["alpha_id"] for root in normalized]
    if len(normalized) != len(roots) or alpha_ids != sorted(alpha_ids):
        raise ValueError("registry bootstrap roots must be complete and sorted")
    for root in normalized:
        if root["status"] == "canonical_dsl":
            formula = root["canonical_formula"]
            if not isinstance(formula, str):
                raise ValueError("canonical registry root has no formula")
            identity = build_expression_identity(formula, grammar=grammar)
            if identity.expression_id != root["expression_id"]:
                raise ValueError("canonical registry root expression identity mismatch")
    expected_snapshot = canonical_json_hash(
        {
            "grammar_version": grammar.semantic_version,
            "grammar_hash": grammar.content_hash,
            "roots": normalized,
        }
    )
    expected_code = canonical_json_hash({"sources": _source_evidence(normalized)})
    if payload["registry_snapshot_hash"] != expected_snapshot:
        raise ValueError("registry snapshot hash mismatch")
    if payload["registry_code_hash"] != expected_code:
        raise ValueError("registry code hash mismatch")
    if payload["snapshot_id"] != "registry-" + expected_snapshot.removeprefix("sha256:")[:16]:
        raise ValueError("registry snapshot ID mismatch")


def _source_evidence(roots: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        {
            "alpha_id": root["alpha_id"],
            "source_hash": root["source_hash"],
            "source_status": root["source_status"],
            "source_reason": root["source_reason"],
        }
        for root in roots
    ]


__all__ = [
    "RegistryBootstrapSource", "build_registry_bootstrap_payload",
    "validate_registry_bootstrap_payload",
]
