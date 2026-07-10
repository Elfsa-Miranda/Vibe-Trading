"""Explicit, dynamic compatibility status for the existing factor registry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from src.alpha_foundry.dsl.identity import FormulaIdentityError, build_expression_identity
from src.research_ledger.hash_utils import canonical_json_hash


class RegistryLike(Protocol):
    def list(self) -> list[str]: ...
    def get(self, alpha_id: str): ...


@dataclass(frozen=True)
class RegistryFormulaCompatibility:
    alpha_id: str
    status: Literal["canonical_dsl", "legacy_opaque"]
    expression_id: str | None
    reason_code: str | None
    legacy_formula_hash: str


def assess_registry_formula_compatibility(registry: RegistryLike) -> list[RegistryFormulaCompatibility]:
    """Classify every runtime registry item without inventing an AST.

    Registry formula metadata is primarily LaTex today.  A formula that is not
    independently parseable by the safe DSL remains an opaque compatibility
    root, so future DAG bootstrap can carry provenance without pretending it
    has canonical structural lineage.
    """
    records: list[RegistryFormulaCompatibility] = []
    for alpha_id in sorted(registry.list()):
        alpha = registry.get(alpha_id)
        formula = alpha.meta.get("formula_latex")
        raw = formula if isinstance(formula, str) else ""
        raw_hash = canonical_json_hash({"formula": raw})
        try:
            identity = build_expression_identity(raw)
        except FormulaIdentityError:
            records.append(RegistryFormulaCompatibility(alpha_id, "legacy_opaque", None, "REGISTRY_FORMULA_NOT_CANONICAL_DSL", raw_hash))
        else:
            records.append(RegistryFormulaCompatibility(alpha_id, "canonical_dsl", identity.expression_id, None, raw_hash))
    return records


__all__ = ["RegistryFormulaCompatibility", "assess_registry_formula_compatibility"]
