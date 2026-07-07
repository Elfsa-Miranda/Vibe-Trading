"""Ordered transform pipeline helpers."""

from __future__ import annotations

from src.alpha_foundry.common.hashing import canonical_hash
from src.alpha_foundry.factors.base import TransformStep


def transform_pipeline_hash(transform_pipeline: list[TransformStep]) -> str:
    return canonical_hash({"transform_pipeline": [step.model_dump(mode="json") for step in transform_pipeline]})

