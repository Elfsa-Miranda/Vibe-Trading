"""Closed policy registry for adaptive falsification evidence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal


APPROVED_SEQUENTIAL_METHOD: Final[Literal["bounded_mean_mixture_e.v1"]] = (
    "bounded_mean_mixture_e.v1"
)
SEQUENTIAL_STOPPING_RULE: Final[Literal["e_process_boundary_or_max_looks.v1"]] = (
    "e_process_boundary_or_max_looks.v1"
)
MECHANISM_EVIDENCE_POLICY_VERSION: Final[Literal["mechanism_evidence_index.v1"]] = (
    "mechanism_evidence_index.v1"
)


@dataclass(frozen=True)
class SequentialMethodAvailability:
    """Typed availability result; it never falls back to repeated p-values."""

    schema_version: Literal["sequential_method_availability.v1"]
    method: str
    status: Literal["approved", "unavailable"]
    reason_code: str


def sequential_method_availability(method: str) -> SequentialMethodAvailability:
    if method == APPROVED_SEQUENTIAL_METHOD:
        return SequentialMethodAvailability(
            "sequential_method_availability.v1",
            method,
            "approved",
            "APPROVED_CONDITIONALLY_VALID_E_PROCESS",
        )
    return SequentialMethodAvailability(
        "sequential_method_availability.v1",
        method,
        "unavailable",
        "SEQUENTIAL_METHOD_NOT_APPROVED",
    )


__all__ = [
    "APPROVED_SEQUENTIAL_METHOD",
    "MECHANISM_EVIDENCE_POLICY_VERSION",
    "SEQUENTIAL_STOPPING_RULE",
    "SequentialMethodAvailability",
    "sequential_method_availability",
]
