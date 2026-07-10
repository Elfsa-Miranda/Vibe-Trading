from __future__ import annotations

from dataclasses import replace

import pytest

from src.alpha_foundry.dsl.canonical import canonicalize_ast, render_canonical_ast
from src.alpha_foundry.dsl.grammar import DEFAULT_GRAMMAR, GrammarDefinition
from src.alpha_foundry.dsl.identity import (
    FormulaIdentityError,
    build_expression_identity,
    build_sign_normalized_identity,
)
from src.alpha_foundry.dsl.model import ASTNode, NumberLiteral


def test_safe_canonical_aliases_whitespace_and_numeric_forms_share_expression_id() -> None:
    left = build_expression_identity(" cs_rank( ts_avg( returns , 05 ) ) ")
    right = build_expression_identity("rank(ts_mean(ret_1d,5))")

    assert left.expression_id == right.expression_id
    assert left.canonical_ast_hash == right.canonical_ast_hash
    assert left.canonical_formula == "rank(ts_mean(ret_1d,5))"


def test_exact_decimal_normalization_is_safe_and_deterministic() -> None:
    integer = build_expression_identity("rank(signed_power(close,2))")
    decimal = build_expression_identity("rank(signed_power(close,2.000))")
    negative_zero = build_expression_identity("rank(signed_power(close,-0.0))")
    zero = build_expression_identity("rank(signed_power(close,0))")

    assert integer.expression_id == decimal.expression_id
    assert negative_zero.expression_id == zero.expression_id


def test_commutative_children_are_sorted_only_for_declared_operators() -> None:
    add_left = build_expression_identity("rank(add(close,open))")
    add_right = build_expression_identity("rank(add(open,close))")
    sub_left = build_expression_identity("rank(sub(close,open))")
    sub_right = build_expression_identity("rank(sub(open,close))")

    assert add_left.expression_id == add_right.expression_id
    assert sub_left.expression_id != sub_right.expression_id


def test_associativity_and_nan_sensitive_noop_forms_remain_distinct() -> None:
    left_nested = build_expression_identity("rank(add(add(close,open),high))")
    right_nested = build_expression_identity("rank(add(close,add(open,high)))")
    explicit_noop = build_expression_identity("rank(add(close,0))")
    plain = build_expression_identity("rank(close)")

    assert left_nested.expression_id != right_nested.expression_id
    assert explicit_noop.expression_id != plain.expression_id


def test_grammar_change_changes_expression_id_without_rewriting_old_identity() -> None:
    old = build_expression_identity("rank(close)")
    next_grammar = DEFAULT_GRAMMAR.with_semantic_version("1.1.0")
    new = build_expression_identity("rank(close)", grammar=next_grammar)

    assert old.grammar_version == "1.0.0"
    assert new.grammar_version == "1.1.0"
    assert old.grammar_hash != new.grammar_hash
    assert old.expression_id != new.expression_id
    assert build_expression_identity("rank(close)").expression_id == old.expression_id


def test_sign_flip_is_not_canonical_identity_but_has_separate_normalized_evidence() -> None:
    positive = build_expression_identity("rank(close)")
    negative = build_expression_identity("neg(rank(close))")
    positive_sign = build_sign_normalized_identity(positive)
    negative_sign = build_sign_normalized_identity(negative)

    assert positive.expression_id != negative.expression_id
    assert positive_sign.sign_normalized_id == negative_sign.sign_normalized_id
    assert positive_sign.polarity == 1
    assert negative_sign.polarity == -1


def test_explicit_negative_one_and_nested_negation_share_only_sign_identity() -> None:
    positive = build_expression_identity("rank(close)")
    multiplied = build_expression_identity("mul(rank(close),-1)")
    double_negative = build_expression_identity("neg(neg(rank(close)))")

    assert multiplied.expression_id != positive.expression_id
    assert build_sign_normalized_identity(multiplied).sign_normalized_id == build_sign_normalized_identity(positive).sign_normalized_id
    assert build_sign_normalized_identity(multiplied).polarity == -1
    assert build_sign_normalized_identity(double_negative).sign_normalized_id == build_sign_normalized_identity(positive).sign_normalized_id
    assert build_sign_normalized_identity(double_negative).polarity == 1


def test_forged_grammar_hash_and_alias_shadowing_fail_closed() -> None:
    raw = DEFAULT_GRAMMAR.to_dict()
    with pytest.raises(ValueError, match="content_hash"):
        GrammarDefinition(
            semantic_version=DEFAULT_GRAMMAR.semantic_version,
            content_hash="sha256:" + "0" * 64,
            operators=DEFAULT_GRAMMAR.operators,
            allowed_fields=DEFAULT_GRAMMAR.allowed_fields,
            operator_aliases=DEFAULT_GRAMMAR.operator_aliases,
            field_aliases=DEFAULT_GRAMMAR.field_aliases,
            max_formula_chars=DEFAULT_GRAMMAR.max_formula_chars,
            max_ast_depth=DEFAULT_GRAMMAR.max_ast_depth,
            max_ast_nodes=DEFAULT_GRAMMAR.max_ast_nodes,
            max_window=DEFAULT_GRAMMAR.max_window,
        )
    raw["operator_aliases"] = {"close": "rank"}
    with pytest.raises(ValueError, match="shadow"):
        GrammarDefinition.from_dict(raw)


def test_direct_noncanonical_number_and_malformed_ast_are_rejected() -> None:
    with pytest.raises(ValueError, match="canonical form"):
        NumberLiteral("01")
    with pytest.raises(ValueError, match="AST_NODE_INVALID"):
        canonicalize_ast(ASTNode("field", args=(NumberLiteral("1"),), value=None))


@pytest.mark.parametrize(
    ("formula", "code"),
    [
        ("delay(close,-1)", "LOOKAHEAD_DETECTED"),
        ("rank(future_return)", "LOOKAHEAD_DETECTED"),
        ("evil(close)", "OPERATOR_NOT_ALLOWED"),
        ("rank(zscore(winsorize(decay_linear(delta(close,2),3))))", "AST_DEPTH_EXCEEDED"),
        ("rank(ts_mean(close,1.5))", "ARGUMENT_TYPE_INVALID"),
    ],
)
def test_invalid_identity_inputs_fail_with_deterministic_codes(formula: str, code: str) -> None:
    with pytest.raises(FormulaIdentityError) as excinfo:
        build_expression_identity(formula)

    assert code in excinfo.value.error_codes


def test_canonical_render_round_trip_preserves_identity_for_generated_safe_forms() -> None:
    formulas = [
        "rank(close)",
        "rank(delta(close,5))",
        "zscore(mul(volume,close))",
        "rank(add(open,close))",
        "clip(zscore(ret_1d),-3.0,3.000)",
        "rank(ts_corr(close,volume,20))",
    ]

    for formula in formulas:
        identity = build_expression_identity(formula)
        rendered = render_canonical_ast(identity.canonical_ast)
        reparsed = build_expression_identity(rendered)
        assert reparsed.expression_id == identity.expression_id
        assert reparsed.canonical_ast == identity.canonical_ast


def test_canonical_ast_is_immutable() -> None:
    identity = build_expression_identity("rank(close)")

    with pytest.raises(TypeError):
        identity.canonical_ast["op"] = "evil"  # type: ignore[index]
