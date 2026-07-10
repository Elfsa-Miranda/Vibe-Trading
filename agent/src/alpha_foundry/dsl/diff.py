"""Auditable structural diffs for immutable canonical safe-DSL ASTs."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Literal, Mapping

from src.alpha_foundry.dsl.canonical import thaw_canonical_ast
from src.research_ledger.hash_utils import canonical_json_hash


OperationKind = Literal["Insert", "Delete", "Replace", "ChangeParameter", "Wrap", "Unwrap"]


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


@dataclass(frozen=True)
class ASTEditOperation:
    kind: OperationKind
    path: tuple[str | int, ...]
    before: Mapping[str, Any] | None
    after: Mapping[str, Any] | None

    def __post_init__(self) -> None:
        if not self.path and self.kind not in {"Replace", "Wrap", "Unwrap"}:
            raise ValueError("only root replacement/wrapping may use an empty path")
        object.__setattr__(self, "before", None if self.before is None else _freeze(dict(self.before)))
        object.__setattr__(self, "after", None if self.after is None else _freeze(dict(self.after)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "path": list(self.path),
            "before": None if self.before is None else thaw_canonical_ast(self.before),
            "after": None if self.after is None else thaw_canonical_ast(self.after),
        }


@dataclass(frozen=True)
class ASTDiff:
    schema_version: Literal["ast_diff.v1"]
    parent_expression_id: str
    child_expression_id: str
    grammar_version: str
    grammar_hash: str
    extractor_version: str
    extractor_hash: str
    operations: tuple[ASTEditOperation, ...]
    normalized_edit_distance: float
    reconstruction_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "parent_expression_id": self.parent_expression_id,
            "child_expression_id": self.child_expression_id,
            "grammar_version": self.grammar_version,
            "grammar_hash": self.grammar_hash,
            "extractor_version": self.extractor_version,
            "extractor_hash": self.extractor_hash,
            "operations": [operation.to_dict() for operation in self.operations],
            "normalized_edit_distance": self.normalized_edit_distance,
            "reconstruction_hash": self.reconstruction_hash,
        }


_EXTRACTOR_VERSION = "ast-diff.v1"
_EXTRACTOR_HASH = canonical_json_hash({"extractor_version": _EXTRACTOR_VERSION, "algorithm": "safe-structural-recursive"})


def extract_ast_diff(
    parent_ast: Mapping[str, Any],
    child_ast: Mapping[str, Any],
    *,
    parent_expression_id: str,
    child_expression_id: str,
    grammar_version: str,
    grammar_hash: str,
) -> ASTDiff:
    parent = thaw_canonical_ast(parent_ast)
    child = thaw_canonical_ast(child_ast)
    operations: list[ASTEditOperation] = []
    _diff(parent, child, (), operations)
    reconstructed = apply_ast_diff(parent, operations)
    reconstruction_hash = canonical_json_hash(reconstructed)
    if reconstruction_hash != canonical_json_hash(child):
        raise ValueError("AST diff failed deterministic reconstruction")
    denominator = max(_node_count(parent), _node_count(child), 1)
    return ASTDiff(
        schema_version="ast_diff.v1",
        parent_expression_id=parent_expression_id,
        child_expression_id=child_expression_id,
        grammar_version=grammar_version,
        grammar_hash=grammar_hash,
        extractor_version=_EXTRACTOR_VERSION,
        extractor_hash=_EXTRACTOR_HASH,
        operations=tuple(operations),
        normalized_edit_distance=len(operations) / denominator,
        reconstruction_hash=reconstruction_hash,
    )


def _diff(parent: dict[str, Any], child: dict[str, Any], path: tuple[str | int, ...], out: list[ASTEditOperation]) -> None:
    if parent == child:
        return
    if child.get("kind") == "call" and len(child.get("args", [])) == 1 and child["args"][0] == parent:
        out.append(ASTEditOperation("Wrap", path, parent, child))
        return
    if parent.get("kind") == "call" and len(parent.get("args", [])) == 1 and parent["args"][0] == child:
        out.append(ASTEditOperation("Unwrap", path, parent, child))
        return
    if parent.get("kind") == "call" and child.get("kind") == "call":
        if parent.get("op") != child.get("op"):
            out.append(ASTEditOperation("Replace", path, parent, child))
            return
        parent_args = parent.get("args", [])
        child_args = child.get("args", [])
        shared = min(len(parent_args), len(child_args))
        for index in range(shared):
            _diff(parent_args[index], child_args[index], path + ("args", index), out)
        for index in range(shared, len(child_args)):
            out.append(ASTEditOperation("Insert", path + ("args", index), None, child_args[index]))
        for index in range(shared, len(parent_args)):
            out.append(ASTEditOperation("Delete", path + ("args", index), parent_args[index], None))
        return
    if parent.get("kind") == child.get("kind") and parent.get("kind") in {"field", "number"}:
        out.append(ASTEditOperation("ChangeParameter", path, parent, child))
        return
    out.append(ASTEditOperation("Replace", path, parent, child))


def apply_ast_diff(parent_ast: Mapping[str, Any], operations: tuple[ASTEditOperation, ...] | list[ASTEditOperation]) -> dict[str, Any]:
    """Apply extractor output only; rejects arbitrary/incomplete edit scripts."""
    current = thaw_canonical_ast(parent_ast)
    for operation in operations:
        if operation.kind in {"Replace", "Wrap", "Unwrap", "ChangeParameter"}:
            if operation.after is None:
                raise ValueError("replacement operation must carry a child node")
            current = _replace_at_path(current, operation.path, thaw_canonical_ast(operation.after))
        elif operation.kind == "Insert":
            if operation.after is None:
                raise ValueError("insert operation must carry a child node")
            current = _insert_at_path(current, operation.path, thaw_canonical_ast(operation.after))
        elif operation.kind == "Delete":
            current = _delete_at_path(current, operation.path)
        else:  # defensive for malformed data deserialized outside this module
            raise ValueError("unknown AST edit operation")
    return current


def ast_diff_from_dict(payload: Mapping[str, Any]) -> ASTDiff:
    if payload.get("schema_version") != "ast_diff.v1":
        raise ValueError("unsupported AST diff schema")
    operations = tuple(
        ASTEditOperation(
            kind=item["kind"],
            path=tuple(item["path"]),
            before=item.get("before"),
            after=item.get("after"),
        )
        for item in payload.get("operations", [])
    )
    if not operations:
        raise ValueError("AST diff cannot be empty")
    return ASTDiff(
        schema_version="ast_diff.v1",
        parent_expression_id=str(payload["parent_expression_id"]),
        child_expression_id=str(payload["child_expression_id"]),
        grammar_version=str(payload["grammar_version"]),
        grammar_hash=str(payload["grammar_hash"]),
        extractor_version=str(payload["extractor_version"]),
        extractor_hash=str(payload["extractor_hash"]),
        operations=operations,
        normalized_edit_distance=float(payload["normalized_edit_distance"]),
        reconstruction_hash=str(payload["reconstruction_hash"]),
    )


def _replace_at_path(root: dict[str, Any], path: tuple[str | int, ...], value: dict[str, Any]) -> dict[str, Any]:
    if not path:
        return value
    target = root
    for key in path[:-1]:
        target = target[key]  # type: ignore[index]
    target[path[-1]] = value  # type: ignore[index]
    return root


def _insert_at_path(root: dict[str, Any], path: tuple[str | int, ...], value: dict[str, Any]) -> dict[str, Any]:
    if len(path) < 2 or path[-2] != "args" or not isinstance(path[-1], int):
        raise ValueError("insert path must address a call argument")
    target = root
    for key in path[:-2]:
        target = target[key]  # type: ignore[index]
    target["args"].insert(path[-1], value)
    return root


def _delete_at_path(root: dict[str, Any], path: tuple[str | int, ...]) -> dict[str, Any]:
    if len(path) < 2 or path[-2] != "args" or not isinstance(path[-1], int):
        raise ValueError("delete path must address a call argument")
    target = root
    for key in path[:-2]:
        target = target[key]  # type: ignore[index]
    del target["args"][path[-1]]
    return root


def _node_count(node: Mapping[str, Any]) -> int:
    return 1 + sum(_node_count(child) for child in node.get("args", []))


__all__ = ["ASTDiff", "ASTEditOperation", "apply_ast_diff", "ast_diff_from_dict", "extract_ast_diff"]
