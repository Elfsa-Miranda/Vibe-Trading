from __future__ import annotations

import pytest

from src.alpha_foundry.dsl.diff import ASTEditOperation, apply_ast_diff, ast_diff_from_dict, extract_ast_diff
from src.alpha_foundry.dsl.canonical import thaw_canonical_ast
from src.alpha_foundry.dsl.identity import build_expression_identity
from src.research_ledger.hash_utils import canonical_json_hash


def test_ast_diff_round_trip_reconstructs_child() -> None:
    parent = build_expression_identity("rank(close)")
    child = build_expression_identity("zscore(rank(close))")
    diff = extract_ast_diff(parent.canonical_ast, child.canonical_ast, parent_expression_id=parent.expression_id, child_expression_id=child.expression_id, grammar_version=child.grammar_version, grammar_hash=child.grammar_hash)

    assert apply_ast_diff(parent.canonical_ast, diff.operations) == thaw_canonical_ast(child.canonical_ast)
    assert diff.reconstruction_hash == canonical_json_hash(thaw_canonical_ast(child.canonical_ast))
    assert diff.operations[0].kind == "Wrap"


def test_parameter_change_and_rehydrated_diff_are_deterministic() -> None:
    parent = build_expression_identity("rank(delta(close,2))")
    child = build_expression_identity("rank(delta(close,5))")
    original = extract_ast_diff(parent.canonical_ast, child.canonical_ast, parent_expression_id=parent.expression_id, child_expression_id=child.expression_id, grammar_version=child.grammar_version, grammar_hash=child.grammar_hash)
    restored = ast_diff_from_dict(original.to_dict())

    assert restored.to_dict() == original.to_dict()
    assert any(operation.kind == "ChangeParameter" for operation in restored.operations)


def test_invalid_or_placeholder_diff_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown or missing"):
        ast_diff_from_dict({"schema_version": "ast_diff.v1", "operations": []})
    with pytest.raises(ValueError, match="insert path"):
        apply_ast_diff({"kind": "field", "name": "close"}, [ASTEditOperation("Insert", ("name",), None, {"kind": "field", "name": "open"})])


def test_diff_rejects_forged_before_extractor_and_reconstruction() -> None:
    parent = build_expression_identity("rank(close)")
    child = build_expression_identity("rank(open)")
    diff = extract_ast_diff(
        parent.canonical_ast, child.canonical_ast,
        parent_expression_id=parent.expression_id,
        child_expression_id=child.expression_id,
        grammar_version=child.grammar_version,
        grammar_hash=child.grammar_hash,
    )
    payload = diff.to_dict()
    payload["extractor_hash"] = canonical_json_hash({"forged": True})
    with pytest.raises(ValueError, match="extractor"):
        ast_diff_from_dict(payload)

    operation = ASTEditOperation(
        "ChangeParameter", (), {"kind": "field", "name": "volume"},
        {"kind": "field", "name": "open"},
    )
    with pytest.raises(ValueError, match="before node"):
        apply_ast_diff({"kind": "field", "name": "close"}, [operation])

    with pytest.raises(ValueError, match="cited child"):
        ast_diff_from_dict(
            diff.to_dict(), parent_ast=parent.canonical_ast,
            child_ast=build_expression_identity("rank(volume)").canonical_ast,
        )
