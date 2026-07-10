"""Deterministic motif extraction from an actual reconstructed AST diff."""

from __future__ import annotations

from dataclasses import dataclass

from src.alpha_foundry.dsl.diff import ASTDiff
from src.research_ledger.hash_utils import canonical_json_hash


@dataclass(frozen=True)
class DerivedMotif:
    motif_version: str
    motif: str
    ast_diff_hash: str


def derive_motif(diff: ASTDiff) -> DerivedMotif:
    if not diff.operations:
        raise ValueError("an empty AST diff cannot become a process motif")
    labels = []
    for operation in diff.operations:
        after = operation.after
        if operation.kind in {"Wrap", "Unwrap"} and after is not None:
            labels.append(f"{operation.kind}:{after.get('op', 'unknown')}")
        else:
            labels.append(operation.kind)
    motif = "+".join(sorted(labels))
    return DerivedMotif(
        motif_version="ast-motif.v1",
        motif=motif,
        ast_diff_hash=canonical_json_hash(diff.to_dict()),
    )


__all__ = ["DerivedMotif", "derive_motif"]
