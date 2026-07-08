"""Append-only JSONL forward observation store."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.alpha_foundry.common.hashing import canonical_hash
from src.alpha_foundry.forward.model import ForwardObservation, with_previous_hash


class ForwardStoreMutationError(ValueError):
    """Raised for forbidden forward-store mutations."""


class ForwardObservationJsonlStore:
    def __init__(self, path: str | Path) -> None:
        self.path = _validate_store_path(Path(path))
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, observation: ForwardObservation) -> ForwardObservation:
        all_observations = self._read_all_observations()
        if any(item.observation_id == observation.observation_id for item in all_observations):
            raise ForwardStoreMutationError("duplicate observation_id rejected")
        existing = self.list_observations(observation.plan_id)
        if existing:
            last = existing[-1]
            if observation.period_start <= last.period_start or observation.period_end <= last.period_end:
                raise ForwardStoreMutationError("out-of-order forward observation append rejected")
            if (
                observation.previous_observation_hash is not None
                and observation.previous_observation_hash != last.observation_hash
            ):
                raise ForwardStoreMutationError("previous_observation_hash does not match current chain head")
            observation = with_previous_hash(observation, last.observation_hash)
        elif observation.previous_observation_hash is not None:
            raise ForwardStoreMutationError("first observation cannot have previous_observation_hash")

        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(observation.model_dump(mode="json"), sort_keys=True, allow_nan=False) + "\n")
        return observation

    def list_observations(self, plan_id: str) -> list[ForwardObservation]:
        return [observation for observation in self._read_all_observations() if observation.plan_id == plan_id]

    def _read_all_observations(self) -> list[ForwardObservation]:
        if not self.path.exists():
            return []
        observations: list[ForwardObservation] = []
        previous_hash_by_plan: dict[str, str] = {}
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            observation = ForwardObservation.model_validate(json.loads(line))
            _validate_observation_hash(observation)
            expected_previous = previous_hash_by_plan.get(observation.plan_id)
            if observation.previous_observation_hash != expected_previous:
                raise ForwardStoreMutationError("previous_observation_hash chain mismatch")
            previous_hash_by_plan[observation.plan_id] = observation.observation_hash
            observations.append(observation)
        return observations


def _validate_store_path(path: Path) -> Path:
    raw = str(path)
    if "://" in raw or any(part == ".." for part in path.parts):
        raise ForwardStoreMutationError("path traversal forward store path rejected")
    expanded = path.expanduser()
    if expanded.exists() and expanded.is_symlink():
        raise ForwardStoreMutationError("symlink forward store path rejected")
    for parent in expanded.parents:
        if parent.exists() and parent.is_symlink():
            raise ForwardStoreMutationError("symlink forward store parent rejected")
    return expanded.resolve(strict=False)


def _validate_observation_hash(observation: ForwardObservation) -> None:
    expected = canonical_hash(_observation_hash_payload(observation))
    if observation.observation_hash != expected:
        raise ForwardStoreMutationError("forward observation hash mismatch")


def _observation_hash_payload(observation: ForwardObservation) -> dict[str, Any]:
    return {
        "observation_id": observation.observation_id,
        "plan_id": observation.plan_id,
        "period_start": observation.period_start.isoformat(),
        "period_end": observation.period_end.isoformat(),
        "realized_rank_ic": observation.realized_rank_ic,
        "realized_return": observation.realized_return,
        "realized_turnover": observation.realized_turnover,
        "realized_cost_bps": observation.realized_cost_bps,
        "previous_observation_hash": observation.previous_observation_hash,
        "created_at": observation.created_at.isoformat(),
        "metadata": observation.metadata,
    }

