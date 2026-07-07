"""Load and validate AlphaHypothesis registries."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import yaml
from pydantic import ValidationError

from src.alpha_foundry.hypothesis.model import AlphaHypothesis


class RegistryValidationError(ValueError):
    """Raised when a hypothesis registry file is malformed."""


def _default_registry_path() -> Path:
    return Path(__file__).with_name("default_registry.yaml")


class AlphaHypothesisRegistry:
    def __init__(self, hypotheses: Iterable[AlphaHypothesis]) -> None:
        self._by_id: dict[str, AlphaHypothesis] = {}
        for hypothesis in hypotheses:
            if hypothesis.hypothesis_id in self._by_id:
                raise RegistryValidationError(f"duplicate hypothesis_id: {hypothesis.hypothesis_id}")
            self._by_id[hypothesis.hypothesis_id] = hypothesis

    @classmethod
    def from_file(cls, path: str | Path) -> "AlphaHypothesisRegistry":
        registry_path = Path(path)
        raw = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or not isinstance(raw.get("hypotheses"), list):
            raise RegistryValidationError("registry file must contain a hypotheses list")

        hypotheses: list[AlphaHypothesis] = []
        seen: set[str] = set()
        for item in raw["hypotheses"]:
            if not isinstance(item, dict):
                raise RegistryValidationError("each hypothesis entry must be a mapping")
            hypothesis_id = item.get("hypothesis_id")
            if hypothesis_id in seen:
                raise RegistryValidationError(f"duplicate hypothesis_id: {hypothesis_id}")
            seen.add(hypothesis_id)
            try:
                hypotheses.append(AlphaHypothesis.model_validate(item))
            except ValidationError as exc:
                raise RegistryValidationError(f"{hypothesis_id}: {exc}") from exc
        return cls(hypotheses)

    @classmethod
    def load_default(cls) -> "AlphaHypothesisRegistry":
        return cls.from_file(_default_registry_path())

    def get(self, hypothesis_id: str) -> AlphaHypothesis:
        try:
            return self._by_id[hypothesis_id]
        except KeyError as exc:
            raise KeyError(f"unknown hypothesis_id: {hypothesis_id}") from exc

    def list(self, *, track: str | None = None) -> list[AlphaHypothesis]:
        hypotheses = self._by_id.values()
        if track is not None:
            hypotheses = [hypothesis for hypothesis in hypotheses if hypothesis.track == track]
        return sorted(hypotheses, key=lambda hypothesis: hypothesis.hypothesis_id)

    def ledger_family_for(self, hypothesis_id: str) -> str:
        return self.get(hypothesis_id).track

    def ledger_sub_family_for(self, hypothesis_id: str) -> str:
        return self.get(hypothesis_id).hypothesis_id

