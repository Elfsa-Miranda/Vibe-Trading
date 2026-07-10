"""Bounded process-local working memory; intentionally never serialized."""

from __future__ import annotations

from collections import deque
from copy import deepcopy
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


@dataclass(frozen=True)
class WorkingCandidate:
    candidate_id: str
    payload: Mapping[str, Any]


class WorkingMemory:
    def __init__(self, *, capacity: int = 256) -> None:
        if capacity < 1:
            raise ValueError("working memory capacity must be positive")
        self.capacity = capacity
        self._items: deque[WorkingCandidate] = deque(maxlen=capacity)
        self._closed = False

    def add(self, candidate_id: str, payload: dict[str, Any]) -> None:
        if self._closed:
            raise RuntimeError("working memory has been destroyed")
        self._items.append(WorkingCandidate(candidate_id, _freeze(deepcopy(payload))))

    def snapshot(self) -> tuple[WorkingCandidate, ...]:
        if self._closed:
            raise RuntimeError("working memory has been destroyed")
        return tuple(self._items)

    def clear(self) -> None:
        self._items.clear()

    def close(self) -> None:
        self.clear()
        self._closed = True

    def __enter__(self) -> "WorkingMemory":
        if self._closed:
            raise RuntimeError("working memory has been destroyed")
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


__all__ = ["WorkingCandidate", "WorkingMemory"]
