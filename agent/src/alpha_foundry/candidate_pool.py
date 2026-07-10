from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.alpha_foundry.dsl.identity import FactorSpecSemantics, build_factor_spec_identity
from src.alpha_quality.flags import ResolvedAGSFlags
from src.research_ledger.hash_utils import canonical_json_hash


@dataclass(frozen=True)
class CandidateExpression:
    candidate_id: str
    parent_seed_id: str
    formula: str
    formula_hash: str
    metadata: dict[str, Any]
    expression_id: str | None = None
    factor_spec_id: str | None = None
    identity_schema_version: str | None = None


def candidate_id_aliases(candidate: CandidateExpression) -> tuple[str, ...]:
    """Return canonical and v3.1 raw-formula IDs for lookup migration.

    The raw identifier is intentionally derived exactly as the v3.1 pool did;
    callers can use this narrow projection to resolve historical references
    without changing either old ledger rows or their hashes.
    """
    legacy_id = candidate.formula_hash.removeprefix("sha256:")[:16]
    return tuple(dict.fromkeys((candidate.candidate_id, legacy_id)))


def candidate_matches_id(candidate: CandidateExpression, candidate_id: str) -> bool:
    """Resolve a public canonical or preserved v3.1 candidate identifier."""
    return candidate_id in candidate_id_aliases(candidate)


def make_candidate(
    parent_seed_id: str,
    formula: str,
    *,
    mutation: str,
    flags: ResolvedAGSFlags | None = None,
    factor_semantics: FactorSpecSemantics | None = None,
) -> CandidateExpression:
    formula_hash = canonical_json_hash({"formula": formula})
    canonical_mode = flags is not None and flags.enabled("VIBE_TRADING_FACTOR_DAG")
    if canonical_mode:
        if factor_semantics is None:
            raise ValueError("factor_semantics is required when canonical identity is enabled")
        identity = build_factor_spec_identity(formula, factor_semantics)
        return CandidateExpression(
            candidate_id=identity.factor_spec_id.removeprefix("sha256:")[:16],
            parent_seed_id=parent_seed_id,
            formula=formula,
            formula_hash=formula_hash,
            metadata={
                "mutation": mutation,
                "legacy_formula_hash": formula_hash,
                "identity_schema_version": "factor_spec.v1",
            },
            expression_id=identity.expression.expression_id,
            factor_spec_id=identity.factor_spec_id,
            identity_schema_version="factor_spec.v1",
        )
    return CandidateExpression(
        candidate_id=formula_hash.removeprefix("sha256:")[:16],
        parent_seed_id=parent_seed_id,
        formula=formula,
        formula_hash=formula_hash,
        metadata={"mutation": mutation},
    )
