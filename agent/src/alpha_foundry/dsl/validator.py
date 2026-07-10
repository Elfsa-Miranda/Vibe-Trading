from __future__ import annotations

from src.alpha_foundry.dsl.grammar import DEFAULT_GRAMMAR, GrammarDefinition
from src.alpha_foundry.dsl.model import ASTNode, NumberLiteral, ValidationResult

# Compatibility constants are retained for v3.1 callers.  Validation itself is
# driven by the versioned grammar passed to ``validate_expression``.
ALLOWED_OPERATORS = {
    "rank",
    "zscore",
    "winsorize",
    "clip",
    "group_neutralize",
    "ts_mean",
    "ts_std",
    "ts_rank",
    "ts_corr",
    "ts_cov",
    "delay",
    "delta",
    "decay_linear",
    "signed_power",
    "add",
    "sub",
    "mul",
    "div_safe",
    "neg",
    "log1p_abs",
    "volume_shock",
    "vwap_deviation",
    "illiquidity_proxy",
}

ALLOWED_FIELDS = {
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
    "vwap",
    "ret_1d",
    "turnover",
    "mktcap",
    "industry",
    "st_flag",
    "suspended",
    "limit_up",
    "limit_down",
}

MAX_AST_DEPTH = 4
MAX_AST_NODES = 12
MAX_WINDOW = 252


def validate_expression(
    node: ASTNode,
    *,
    grammar: GrammarDefinition = DEFAULT_GRAMMAR,
) -> ValidationResult:
    errors: list[str] = []
    if not isinstance(node, ASTNode):
        return ValidationResult(ok=False, errors=("AST_NODE_INVALID",))
    if node.depth > grammar.max_ast_depth:
        errors.append("AST_DEPTH_EXCEEDED")
    if node.node_count > grammar.max_ast_nodes:
        errors.append("AST_NODE_LIMIT_EXCEEDED")
    for op in node.operators():
        if op not in grammar.operators:
            errors.append("OPERATOR_NOT_ALLOWED")
    for field in node.fields():
        if _is_lookahead_field(field):
            errors.append("LOOKAHEAD_DETECTED")
        if field not in grammar.allowed_fields:
            errors.append("FIELD_NOT_ALLOWED")
    _check_signatures(node, grammar, errors)
    return ValidationResult(ok=not errors, errors=tuple(sorted(set(errors))))


def _check_signatures(
    node: ASTNode,
    grammar: GrammarDefinition,
    errors: list[str],
) -> None:
    if not isinstance(node.op, str) or not node.op:
        errors.append("AST_NODE_INVALID")
        return
    if not isinstance(node.args, tuple):
        errors.append("AST_NODE_INVALID")
        return
    if node.op == "field":
        if node.args or not isinstance(node.value, str) or not node.value:
            errors.append("AST_NODE_INVALID")
            return
        if _is_lookahead_field(node.value):
            errors.append("LOOKAHEAD_DETECTED")
        if node.value not in grammar.allowed_fields:
            errors.append("FIELD_NOT_ALLOWED")
        return
    if node.value is not None:
        errors.append("AST_NODE_INVALID")
    spec = grammar.operators.get(node.op)
    if spec is None:
        errors.append("OPERATOR_NOT_ALLOWED")
    if spec is not None:
        if len(node.args) != len(spec.argument_kinds):
            errors.append("ARGUMENT_COUNT_INVALID")
        for index, kind in enumerate(spec.argument_kinds):
            if index >= len(node.args):
                continue
            argument = node.args[index]
            if kind == "expression":
                # Fields are leaf expressions in this DSL; only a scalar
                # literal is invalid in an expression position.
                if not isinstance(argument, ASTNode):
                    errors.append("ARGUMENT_TYPE_INVALID")
            elif kind == "expression_or_number":
                if not isinstance(argument, (ASTNode, NumberLiteral)):
                    errors.append("ARGUMENT_TYPE_INVALID")
            elif kind == "field":
                if not isinstance(argument, ASTNode) or argument.op != "field":
                    errors.append("ARGUMENT_TYPE_INVALID")
            elif kind == "number":
                if not isinstance(argument, NumberLiteral):
                    errors.append("ARGUMENT_TYPE_INVALID")
            elif kind == "positive_integer":
                if not isinstance(argument, NumberLiteral) or not argument.is_integer:
                    errors.append("ARGUMENT_TYPE_INVALID")
                else:
                    value = int(argument.decimal)
                    if node.op == "delay" and value < 0:
                        errors.append("LOOKAHEAD_DETECTED")
                    if value < 1 or value > grammar.max_window:
                        errors.append("WINDOW_OUT_OF_RANGE")
    for arg in node.args:
        if isinstance(arg, ASTNode):
            _check_signatures(arg, grammar, errors)
        elif not isinstance(arg, NumberLiteral):
            errors.append("AST_NODE_INVALID")


def _is_lookahead_field(field: str) -> bool:
    lowered = field.lower()
    return (
        lowered.startswith("future_")
        or lowered.startswith("next_")
        or "_next" in lowered
        or lowered.endswith("_next")
        or lowered.startswith("fwd_")
        or lowered.endswith("_fwd")
        or "t_plus" in lowered
        or "lead" in lowered
    )
