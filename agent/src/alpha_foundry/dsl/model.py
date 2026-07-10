from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any


def _normalize_decimal_token(token: str) -> str:
    if not isinstance(token, str) or not token:
        raise ValueError("invalid numeric literal")
    try:
        value = Decimal(token)
    except InvalidOperation as exc:
        raise ValueError("invalid numeric literal") from exc
    if not value.is_finite():
        raise ValueError("non-finite numeric literal")
    if value == 0:
        return "0"
    normalized = value.normalize()
    if normalized == normalized.to_integral_value():
        return str(int(normalized))
    return format(normalized, "f").rstrip("0").rstrip(".")

@dataclass(frozen=True)
class NumberLiteral:
    canonical: str

    def __post_init__(self) -> None:
        if not isinstance(self.canonical, str) or not self.canonical:
            raise ValueError("numeric literal must be a non-empty canonical string")
        try:
            normalized = _normalize_decimal_token(self.canonical)
        except ValueError as exc:
            raise ValueError("numeric literal is not finite canonical decimal") from exc
        if normalized != self.canonical:
            raise ValueError("numeric literal is not in canonical form")

    @classmethod
    def from_token(cls, token: str) -> "NumberLiteral":
        return cls(_normalize_decimal_token(token))

    @property
    def decimal(self) -> Decimal:
        return Decimal(self.canonical)

    @property
    def is_integer(self) -> bool:
        return self.decimal == self.decimal.to_integral_value()

    def to_number(self) -> int | float:
        return int(self.decimal) if self.is_integer else float(self.decimal)


@dataclass(frozen=True)
class ASTNode:
    op: str
    args: tuple[Any, ...] = ()
    value: str | int | float | None = None

    @property
    def depth(self) -> int:
        child_depths = [
            arg.depth for arg in self.args if isinstance(arg, ASTNode)
        ]
        return 1 + (max(child_depths) if child_depths else 0)

    @property
    def node_count(self) -> int:
        return 1 + sum(
            arg.node_count if isinstance(arg, ASTNode) else 1
            for arg in self.args
            if isinstance(arg, (ASTNode, NumberLiteral))
        )

    def operators(self) -> set[str]:
        ops = set()
        if self.op != "field":
            ops.add(self.op)
        for arg in self.args:
            if isinstance(arg, ASTNode):
                ops |= arg.operators()
        return ops

    def fields(self) -> set[str]:
        output: set[str] = set()
        if self.op == "field" and isinstance(self.value, str):
            output.add(self.value)
        for arg in self.args:
            if isinstance(arg, ASTNode):
                output |= arg.fields()
        return output

    def windows(self) -> list[int]:
        values: list[int] = []
        for arg in self.args:
            if isinstance(arg, NumberLiteral) and arg.is_integer:
                values.append(int(arg.decimal))
            elif isinstance(arg, ASTNode):
                values.extend(arg.windows())
        return values


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    errors: tuple[str, ...]
