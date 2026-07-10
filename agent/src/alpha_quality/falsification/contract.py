"""Immutable legacy-compatible falsification contract."""

from __future__ import annotations

import math
from dataclasses import dataclass

from src.research_ledger.hash_utils import canonical_json_hash


@dataclass(frozen=True)
class FalsificationContract:
    """The v3.1/v3.2 fixed-contract payload whose hash semantics are stable.

    Sequential execution uses a separate ``SequentialProtocol`` companion.  A
    contract carrying a non-fixed stopping declaration remains hashable for
    historical compatibility, but it cannot enter the fixed executor service.
    """

    factor_spec_id: str
    capability_hash: str
    estimand: str
    direction: str
    sesoi: float
    units: str
    sample_unit: str
    conditioning_hash: str
    regime_hash: str
    family_id: str
    alpha: float
    dependence_method: str
    maximum_looks: int
    stopping_rule: str
    decisive: bool
    policy_hash: str

    def __post_init__(self) -> None:
        if (
            not math.isfinite(self.sesoi)
            or self.sesoi <= 0
            or not math.isfinite(self.alpha)
            or not 0 < self.alpha < 1
            or isinstance(self.maximum_looks, bool)
            or self.maximum_looks < 1
        ):
            raise ValueError("invalid frozen falsification contract")

    @property
    def contract_hash(self) -> str:
        # Keep the existing dataclass field-only hash contract unchanged.
        return canonical_json_hash(self.__dict__)

    @property
    def contract_id(self) -> str:
        return "contract-" + self.contract_hash.removeprefix("sha256:")[:16]

    @property
    def is_fixed_horizon(self) -> bool:
        return self.maximum_looks == 1 and self.stopping_rule == "fixed"

    def require_fixed_horizon(self) -> None:
        if not self.is_fixed_horizon:
            raise ValueError(
                "fixed result service requires maximum_looks=1 and stopping_rule='fixed'"
            )


__all__ = ["FalsificationContract"]
