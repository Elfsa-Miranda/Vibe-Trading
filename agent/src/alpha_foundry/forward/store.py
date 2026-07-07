"""Append-only JSONL forward observation store."""

from __future__ import annotations

import json
from pathlib import Path

from src.alpha_foundry.forward.model import ForwardObservation, with_previous_hash


class ForwardStoreMutationError(ValueError):
    """Raised for forbidden update/delete/out-of-order mutations."""


class ForwardObservationJsonlStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, observation: ForwardObservation) -> ForwardObservation:
        existing = self.list_observations(observation.plan_id)
        if existing:
            last = existing[-1]
            if observation.period_start <= last.period_start or observation.period_end <= last.period_end:
                raise ForwardStoreMutationError("out-of-order forward observation append rejected")
            observation = with_previous_hash(observation, last.observation_hash)
        elif observation.previous_observation_hash is not None:
            raise ForwardStoreMutationError("first observation cannot have previous_observation_hash")

        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(observation.model_dump(mode="json"), sort_keys=True, allow_nan=False) + "\n")
        return observation

    def list_observations(self, plan_id: str) -> list[ForwardObservation]:
        if not self.path.exists():
            return []
        observations: list[ForwardObservation] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            observation = ForwardObservation.model_validate(json.loads(line))
            if observation.plan_id == plan_id:
                observations.append(observation)
        return observations

    def update(self, observation: ForwardObservation) -> None:
        raise ForwardStoreMutationError("forward observations are append-only; update is forbidden")

    def delete(self, observation_id: str) -> None:
        raise ForwardStoreMutationError("forward observations are append-only; delete is forbidden")

