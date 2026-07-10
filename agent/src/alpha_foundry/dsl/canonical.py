"""Deterministic, conservative canonical AST representation.

Only grammar-declared aliases, exact numeric spellings, and commutative child
ordering are normalized.  In particular, no algebraic reassociation or
constant folding is performed because those transformations can alter missing
value and finite-value semantics.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

from src.alpha_foundry.dsl.grammar import DEFAULT_GRAMMAR, GrammarDefinition
from src.alpha_foundry.dsl.model import ASTNode, NumberLiteral
from src.research_ledger.hash_utils import canonical_json


CanonicalAST = Mapping[str, Any]


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def thaw_canonical_ast(value: Any) -> Any:
    """Return a JSON-compatible copy for hashing or event payloads."""
    if isinstance(value, Mapping):
        return {str(key): thaw_canonical_ast(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [thaw_canonical_ast(item) for item in value]
    return value


def canonicalize_ast(
    node: ASTNode | NumberLiteral,
    *,
    grammar: GrammarDefinition = DEFAULT_GRAMMAR,
) -> CanonicalAST:
    if isinstance(node, NumberLiteral):
        return _freeze({"kind": "number", "value": node.canonical})
    if node.op == "field":
        return _freeze({"kind": "field", "name": str(node.value)})
    args = [canonicalize_ast(arg, grammar=grammar) for arg in node.args]
    spec = grammar.operators.get(node.op)
    if spec is not None and spec.commutative:
        args.sort(key=lambda item: canonical_json(thaw_canonical_ast(item)))
    return _freeze({"kind": "call", "op": node.op, "args": args})


def render_canonical_ast(ast: Mapping[str, Any]) -> str:
    """Render a canonical AST back to the intentionally small safe DSL."""
    kind = ast.get("kind")
    if kind == "number":
        value = ast.get("value")
        if not isinstance(value, str):
            raise ValueError("canonical number literal is malformed")
        return value
    if kind == "field":
        name = ast.get("name")
        if not isinstance(name, str):
            raise ValueError("canonical field is malformed")
        return name
    if kind == "call":
        op = ast.get("op")
        args = ast.get("args")
        if not isinstance(op, str) or not isinstance(args, (list, tuple)):
            raise ValueError("canonical call is malformed")
        return f"{op}({','.join(render_canonical_ast(arg) for arg in args)})"
    raise ValueError("unknown canonical AST node kind")


__all__ = ["CanonicalAST", "canonicalize_ast", "render_canonical_ast", "thaw_canonical_ast"]
