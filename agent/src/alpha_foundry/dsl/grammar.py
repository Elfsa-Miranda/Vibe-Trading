"""Versioned declarative grammar identity for the safe factor DSL."""

from __future__ import annotations

from dataclasses import dataclass
import re
from types import MappingProxyType
from typing import Any, Literal, Mapping

from src.research_ledger.hash_utils import canonical_json_hash


ArgumentKind = Literal[
    "expression", "expression_or_number", "field", "number", "positive_integer"
]

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ARGUMENT_KINDS = frozenset(
    {"expression", "expression_or_number", "field", "number", "positive_integer"}
)


@dataclass(frozen=True)
class OperatorSpec:
    argument_kinds: tuple[ArgumentKind, ...]
    commutative: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.argument_kinds, tuple) or not self.argument_kinds:
            raise ValueError("operator argument_kinds must be a non-empty tuple")
        if any(kind not in _ARGUMENT_KINDS for kind in self.argument_kinds):
            raise ValueError("operator contains an unknown argument kind")
        if not isinstance(self.commutative, bool):
            raise ValueError("operator commutative must be boolean")

    def to_dict(self) -> dict[str, object]:
        return {
            "argument_kinds": list(self.argument_kinds),
            "commutative": self.commutative,
        }


@dataclass(frozen=True)
class GrammarDefinition:
    semantic_version: str
    content_hash: str
    operators: Mapping[str, OperatorSpec]
    allowed_fields: frozenset[str]
    operator_aliases: Mapping[str, str]
    field_aliases: Mapping[str, str]
    max_formula_chars: int
    max_ast_depth: int
    max_ast_nodes: int
    max_window: int

    def __post_init__(self) -> None:
        operator_copy = dict(self.operators)
        field_copy = frozenset(self.allowed_fields)
        operator_alias_copy = dict(self.operator_aliases)
        field_alias_copy = dict(self.field_aliases)
        _validate_grammar_parts(
            semantic_version=self.semantic_version,
            operators=operator_copy,
            allowed_fields=field_copy,
            operator_aliases=operator_alias_copy,
            field_aliases=field_alias_copy,
            max_formula_chars=self.max_formula_chars,
            max_ast_depth=self.max_ast_depth,
            max_ast_nodes=self.max_ast_nodes,
            max_window=self.max_window,
        )
        expected = canonical_json_hash(
            _grammar_content(
                semantic_version=self.semantic_version,
                operators=operator_copy,
                allowed_fields=field_copy,
                operator_aliases=operator_alias_copy,
                field_aliases=field_alias_copy,
                max_formula_chars=self.max_formula_chars,
                max_ast_depth=self.max_ast_depth,
                max_ast_nodes=self.max_ast_nodes,
                max_window=self.max_window,
            )
        )
        if self.content_hash != expected:
            raise ValueError("grammar content_hash does not match its deterministic content")
        object.__setattr__(self, "operators", MappingProxyType(operator_copy))
        object.__setattr__(self, "allowed_fields", field_copy)
        object.__setattr__(self, "operator_aliases", MappingProxyType(operator_alias_copy))
        object.__setattr__(self, "field_aliases", MappingProxyType(field_alias_copy))

    @classmethod
    def create(
        cls,
        *,
        semantic_version: str,
        operators: Mapping[str, OperatorSpec],
        allowed_fields: frozenset[str],
        operator_aliases: Mapping[str, str],
        field_aliases: Mapping[str, str],
        max_formula_chars: int = 512,
        max_ast_depth: int = 4,
        max_ast_nodes: int = 12,
        max_window: int = 252,
    ) -> "GrammarDefinition":
        operator_copy = dict(operators)
        field_copy = frozenset(allowed_fields)
        operator_alias_copy = dict(operator_aliases)
        field_alias_copy = dict(field_aliases)
        _validate_grammar_parts(
            semantic_version=semantic_version, operators=operator_copy,
            allowed_fields=field_copy, operator_aliases=operator_alias_copy,
            field_aliases=field_alias_copy, max_formula_chars=max_formula_chars,
            max_ast_depth=max_ast_depth, max_ast_nodes=max_ast_nodes,
            max_window=max_window,
        )
        content = _grammar_content(
            semantic_version=semantic_version, operators=operator_copy,
            allowed_fields=field_copy, operator_aliases=operator_alias_copy,
            field_aliases=field_alias_copy, max_formula_chars=max_formula_chars,
            max_ast_depth=max_ast_depth, max_ast_nodes=max_ast_nodes,
            max_window=max_window,
        )
        return cls(
            semantic_version=semantic_version,
            content_hash=canonical_json_hash(content),
            operators=MappingProxyType(operator_copy),
            allowed_fields=field_copy,
            operator_aliases=MappingProxyType(operator_alias_copy),
            field_aliases=MappingProxyType(field_alias_copy),
            max_formula_chars=max_formula_chars,
            max_ast_depth=max_ast_depth,
            max_ast_nodes=max_ast_nodes,
            max_window=max_window,
        )

    def with_semantic_version(self, semantic_version: str) -> "GrammarDefinition":
        return GrammarDefinition.create(
            semantic_version=semantic_version,
            operators=self.operators,
            allowed_fields=self.allowed_fields,
            operator_aliases=self.operator_aliases,
            field_aliases=self.field_aliases,
            max_formula_chars=self.max_formula_chars,
            max_ast_depth=self.max_ast_depth,
            max_ast_nodes=self.max_ast_nodes,
            max_window=self.max_window,
        )

    def to_dict(self) -> dict[str, object]:
        return _grammar_content(
            semantic_version=self.semantic_version, operators=self.operators,
            allowed_fields=self.allowed_fields, operator_aliases=self.operator_aliases,
            field_aliases=self.field_aliases, max_formula_chars=self.max_formula_chars,
            max_ast_depth=self.max_ast_depth, max_ast_nodes=self.max_ast_nodes,
            max_window=self.max_window,
        )

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "GrammarDefinition":
        expected = {
            "semantic_version", "operators", "allowed_fields", "operator_aliases",
            "field_aliases", "limits",
        }
        if set(raw) != expected:
            raise ValueError("grammar snapshot fields are not closed")
        operators_raw = raw["operators"]
        limits = raw["limits"]
        if not isinstance(operators_raw, Mapping) or not isinstance(limits, Mapping):
            raise ValueError("grammar snapshot mappings are malformed")
        if set(limits) != {"max_formula_chars", "max_ast_depth", "max_ast_nodes", "max_window"}:
            raise ValueError("grammar snapshot limits are not closed")
        operators: dict[str, OperatorSpec] = {}
        for name, spec_raw in operators_raw.items():
            if not isinstance(name, str) or not isinstance(spec_raw, Mapping):
                raise ValueError("grammar operator snapshot is malformed")
            if set(spec_raw) != {"argument_kinds", "commutative"}:
                raise ValueError("grammar operator snapshot fields are not closed")
            kinds = spec_raw["argument_kinds"]
            if not isinstance(kinds, (list, tuple)) or any(not isinstance(item, str) for item in kinds):
                raise ValueError("grammar operator argument kinds are malformed")
            operators[name] = OperatorSpec(tuple(kinds), spec_raw["commutative"])  # type: ignore[arg-type]
        fields = raw["allowed_fields"]
        operator_aliases = raw["operator_aliases"]
        field_aliases = raw["field_aliases"]
        if not isinstance(fields, (list, tuple)) or any(not isinstance(item, str) for item in fields):
            raise ValueError("grammar allowed fields are malformed")
        if not isinstance(operator_aliases, Mapping) or not isinstance(field_aliases, Mapping):
            raise ValueError("grammar aliases are malformed")
        return cls.create(
            semantic_version=raw["semantic_version"],  # type: ignore[arg-type]
            operators=operators, allowed_fields=frozenset(fields),
            operator_aliases=dict(operator_aliases), field_aliases=dict(field_aliases),
            max_formula_chars=limits["max_formula_chars"],  # type: ignore[arg-type]
            max_ast_depth=limits["max_ast_depth"],  # type: ignore[arg-type]
            max_ast_nodes=limits["max_ast_nodes"],  # type: ignore[arg-type]
            max_window=limits["max_window"],  # type: ignore[arg-type]
        )

    def canonical_operator(self, name: str) -> str:
        return self.operator_aliases.get(name, name)

    def canonical_field(self, name: str) -> str:
        return self.field_aliases.get(name, name)


def _validate_grammar_parts(
    *, semantic_version: str, operators: Mapping[str, OperatorSpec],
    allowed_fields: frozenset[str], operator_aliases: Mapping[str, str],
    field_aliases: Mapping[str, str], max_formula_chars: int,
    max_ast_depth: int, max_ast_nodes: int, max_window: int,
) -> None:
    if not semantic_version or any(char.isspace() for char in semantic_version):
        raise ValueError("grammar semantic_version must be non-empty and whitespace-free")
    names = (*operators, *allowed_fields, *operator_aliases, *field_aliases)
    if any(not isinstance(name, str) or not _IDENTIFIER_RE.fullmatch(name) for name in names):
        raise ValueError("grammar names must be safe identifiers")
    if not operators or not allowed_fields:
        raise ValueError("grammar operators and fields must be non-empty")
    if any(not isinstance(spec, OperatorSpec) for spec in operators.values()):
        raise ValueError("grammar operators must use OperatorSpec")
    if set(operators) & set(allowed_fields):
        raise ValueError("operator and field names cannot collide")
    if set(operator_aliases) & (set(operators) | set(allowed_fields) | set(field_aliases)):
        raise ValueError("operator aliases cannot shadow canonical names or field aliases")
    if set(field_aliases) & (set(operators) | set(allowed_fields)):
        raise ValueError("field aliases cannot shadow canonical names")
    if any(target not in operators for target in operator_aliases.values()):
        raise ValueError("operator alias targets must exist in the grammar")
    if any(target not in allowed_fields for target in field_aliases.values()):
        raise ValueError("field alias targets must exist in the grammar")
    limits = (max_formula_chars, max_ast_depth, max_ast_nodes, max_window)
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 1 for value in limits):
        raise ValueError("grammar limits must be positive integers")
    if max_formula_chars > 4096 or max_ast_depth > 64 or max_ast_nodes > 4096 or max_window > 10000:
        raise ValueError("grammar limits exceed the deterministic safety ceiling")
    if max_ast_nodes < max_ast_depth:
        raise ValueError("max_ast_nodes cannot be smaller than max_ast_depth")


def _grammar_content(
    *, semantic_version: str, operators: Mapping[str, OperatorSpec],
    allowed_fields: frozenset[str], operator_aliases: Mapping[str, str],
    field_aliases: Mapping[str, str], max_formula_chars: int,
    max_ast_depth: int, max_ast_nodes: int, max_window: int,
) -> dict[str, object]:
    return {
        "semantic_version": semantic_version,
        "operators": {name: spec.to_dict() for name, spec in sorted(operators.items())},
        "allowed_fields": sorted(allowed_fields),
        "operator_aliases": dict(sorted(operator_aliases.items())),
        "field_aliases": dict(sorted(field_aliases.items())),
        "limits": {
            "max_formula_chars": max_formula_chars, "max_ast_depth": max_ast_depth,
            "max_ast_nodes": max_ast_nodes, "max_window": max_window,
        },
    }


_OPERATORS = {
    "rank": OperatorSpec(("expression",)),
    "zscore": OperatorSpec(("expression",)),
    "winsorize": OperatorSpec(("expression",)),
    "clip": OperatorSpec(("expression", "number", "number")),
    "group_neutralize": OperatorSpec(("expression", "field")),
    "ts_mean": OperatorSpec(("expression", "positive_integer")),
    "ts_std": OperatorSpec(("expression", "positive_integer")),
    "ts_rank": OperatorSpec(("expression", "positive_integer")),
    "ts_corr": OperatorSpec(("expression", "expression", "positive_integer")),
    "ts_cov": OperatorSpec(("expression", "expression", "positive_integer")),
    "delay": OperatorSpec(("expression", "positive_integer")),
    "delta": OperatorSpec(("expression", "positive_integer")),
    "decay_linear": OperatorSpec(("expression", "positive_integer")),
    "signed_power": OperatorSpec(("expression", "number")),
    "add": OperatorSpec(("expression", "expression_or_number"), commutative=True),
    "sub": OperatorSpec(("expression", "expression_or_number")),
    "mul": OperatorSpec(("expression", "expression_or_number"), commutative=True),
    "div_safe": OperatorSpec(("expression", "expression_or_number")),
    "neg": OperatorSpec(("expression",)),
    "log1p_abs": OperatorSpec(("expression",)),
    "volume_shock": OperatorSpec(("expression", "positive_integer")),
    "vwap_deviation": OperatorSpec(("expression", "expression")),
    "illiquidity_proxy": OperatorSpec(("expression",)),
}

_FIELDS = frozenset(
    {
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
)

DEFAULT_GRAMMAR = GrammarDefinition.create(
    semantic_version="1.0.0",
    operators=_OPERATORS,
    allowed_fields=_FIELDS,
    operator_aliases={
        "cs_rank": "rank",
        "standardize": "zscore",
        "ts_avg": "ts_mean",
        "divide": "div_safe",
    },
    field_aliases={
        "returns": "ret_1d",
        "return_1d": "ret_1d",
        "vol": "volume",
        "dollar_volume": "amount",
    },
)


__all__ = [
    "ArgumentKind",
    "DEFAULT_GRAMMAR",
    "GrammarDefinition",
    "OperatorSpec",
]
