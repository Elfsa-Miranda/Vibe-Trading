"""Versioned declarative grammar identity for the safe factor DSL."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, Mapping

from src.research_ledger.hash_utils import canonical_json_hash


ArgumentKind = Literal[
    "expression", "expression_or_number", "field", "number", "positive_integer"
]


@dataclass(frozen=True)
class OperatorSpec:
    argument_kinds: tuple[ArgumentKind, ...]
    commutative: bool = False

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
        if not semantic_version or any(char.isspace() for char in semantic_version):
            raise ValueError("grammar semantic_version must be non-empty and whitespace-free")
        operator_copy = dict(operators)
        operator_alias_copy = dict(operator_aliases)
        field_alias_copy = dict(field_aliases)
        if any(target not in operator_copy for target in operator_alias_copy.values()):
            raise ValueError("operator alias targets must exist in the grammar")
        if any(target not in allowed_fields for target in field_alias_copy.values()):
            raise ValueError("field alias targets must exist in the grammar")
        content = {
            "semantic_version": semantic_version,
            "operators": {
                name: spec.to_dict() for name, spec in sorted(operator_copy.items())
            },
            "allowed_fields": sorted(allowed_fields),
            "operator_aliases": dict(sorted(operator_alias_copy.items())),
            "field_aliases": dict(sorted(field_alias_copy.items())),
            "limits": {
                "max_formula_chars": max_formula_chars,
                "max_ast_depth": max_ast_depth,
                "max_ast_nodes": max_ast_nodes,
                "max_window": max_window,
            },
        }
        return cls(
            semantic_version=semantic_version,
            content_hash=canonical_json_hash(content),
            operators=MappingProxyType(operator_copy),
            allowed_fields=frozenset(allowed_fields),
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

    def canonical_operator(self, name: str) -> str:
        return self.operator_aliases.get(name, name)

    def canonical_field(self, name: str) -> str:
        return self.field_aliases.get(name, name)


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
