"""Bounded process-local working memory; intentionally never serialized."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class WorkingCandidate:
    candidate_id: str
    payload: dict[str, Any]


class WorkingMemory:
    def __init__(self, *, capacity: int = 256) -> None:
        if capacity < 1:
            raise ValueError("working memory capacity must be positive")
        self.capacity = capacity
        self._items: deque[WorkingCandidate] = deque(maxlen=capacity)

    def add(self, candidate_id: str, payload: dict[str, Any]) -> None:
        self._items.append(WorkingCandidate(candidate_id, dict(payload)))

    def snapshot(self) -> tuple[WorkingCandidate, ...]:
        return tuple(self._items)

    def clear(self) -> None:
        self._items.clear()


__all__ = ["WorkingCandidate", "WorkingMemory"]
