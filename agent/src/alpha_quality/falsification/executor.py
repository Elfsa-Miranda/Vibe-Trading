"""Closed fixed-horizon mechanism-evidence classification."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, Sequence

from src.alpha_quality.falsification.equivalence import EquivalenceResult, tost
from src.alpha_quality.falsification.multiplicity import MultiplicityMethod, adjust
from src.alpha_quality.flags import ResolvedAGSFlags

EvidenceOutcome = Literal["falsified", "inconclusive", "partial_support", "supported"]


@dataclass(frozen=True)
class FixedTestEvidence:
    test_id: str
    prediction: Literal["positive", "negative", "equivalent"]
    decisive: bool
    effective_n: int
    minimum_effective_n: int
    raw_p_value: float | None = None
    effect: float | None = None
    minimum_effect: float = 0.0
    lower_tost_p: float | None = None
    upper_tost_p: float | None = None
    available: bool = True
    unavailability_code: str | None = None

    def __post_init__(self) -> None:
        if not self.test_id or self.minimum_effective_n < 1 or self.effective_n < 0:
            raise ValueError("invalid fixed test evidence identity or sample")
        probabilities = [value for value in (self.raw_p_value, self.lower_tost_p, self.upper_tost_p) if value is not None]
        if any(not math.isfinite(value) or not 0 <= value <= 1 for value in probabilities):
            raise ValueError("test p-values must be finite probabilities")
        if self.effect is not None and not math.isfinite(self.effect):
            raise ValueError("test effect must be finite")
        if not math.isfinite(self.minimum_effect) or self.minimum_effect < 0:
            raise ValueError("minimum effect must be finite and non-negative")


@dataclass(frozen=True)
class FixedFamilyResult:
    schema_version: Literal["fixed_falsification_result.v1"]
    outcome: EvidenceOutcome
    cap: str | None
    adjusted_p_values: tuple[tuple[str, float], ...]
    equivalence_results: tuple[tuple[str, EquivalenceResult], ...]
    warnings: tuple[str, ...]
    failure_codes: tuple[str, ...]
    multiplicity_method: MultiplicityMethod

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "outcome": self.outcome,
            "cap": self.cap,
            "adjusted_p_values": [list(item) for item in self.adjusted_p_values],
            "equivalence_results": [
                {
                    "test_id": test_id,
                    "estimate": result.estimate,
                    "standard_error": result.standard_error,
                    "margin": result.margin,
                    "alpha": result.alpha,
                    "lower_p_value": result.lower_p_value,
                    "upper_p_value": result.upper_p_value,
                    "confidence_interval": list(result.confidence_interval),
                    "equivalent": result.equivalent,
                    "inconclusive": result.inconclusive,
                    "reason_codes": list(result.reason_codes),
                }
                for test_id, result in self.equivalence_results
            ],
            "warnings": list(self.warnings),
            "failure_codes": list(self.failure_codes),
            "multiplicity_method": self.multiplicity_method,
        }


class FixedHorizonExecutor:
    """Feature-gated production entry point; all judgments remain deterministic."""

    def __init__(self, *, flags: ResolvedAGSFlags) -> None:
        if not flags.enabled("VIBE_TRADING_FALSIFICATION_CONTRACT"):
            raise RuntimeError("fixed-horizon falsification capability is disabled")

    def execute(
        self,
        tests: Sequence[FixedTestEvidence],
        *,
        alpha: float,
        multiplicity_method: MultiplicityMethod = "holm",
    ) -> FixedFamilyResult:
        return execute_fixed_family(tests, alpha=alpha, multiplicity_method=multiplicity_method)


def execute_fixed_family(
    tests: Sequence[FixedTestEvidence], *, alpha: float, multiplicity_method: MultiplicityMethod = "holm",
) -> FixedFamilyResult:
    if not tests or not 0 < alpha < 0.5:
        raise ValueError("fixed family and alpha are required")
    if len({test.test_id for test in tests}) != len(tests):
        raise ValueError("test IDs must be unique within a frozen family")
    warnings: set[str] = set()
    failures: set[str] = set()
    decisive_inconclusive = False
    equivalence: list[tuple[str, EquivalenceResult]] = []
    ordinary = [test for test in tests if test.available and test.prediction != "equivalent" and test.raw_p_value is not None]
    adjusted_values = adjust([test.raw_p_value for test in ordinary if test.raw_p_value is not None], multiplicity_method)
    adjusted = {test.test_id: value for test, value in zip(ordinary, adjusted_values, strict=True)}
    support_count = 0
    decisive_count = 0
    for test in tests:
        if test.decisive:
            decisive_count += 1
        if not test.available:
            code = test.unavailability_code or "TEST_UNAVAILABLE"
            warnings.add(code)
            decisive_inconclusive |= test.decisive
            continue
        if test.effective_n < test.minimum_effective_n:
            warnings.add("LOW_POWER")
            decisive_inconclusive |= test.decisive
            continue
        if test.prediction == "equivalent":
            if test.lower_tost_p is None or test.upper_tost_p is None:
                warnings.add("EQUIVALENCE_COMPONENT_MISSING")
                decisive_inconclusive |= test.decisive
                continue
            result = tost(
                lower_p=test.lower_tost_p, upper_p=test.upper_tost_p, alpha=alpha,
                effective_n=test.effective_n, min_effective_n=test.minimum_effective_n,
            )
            equivalence.append((test.test_id, result))
            if result.equivalent:
                support_count += 1
            elif test.decisive:
                decisive_inconclusive = True
            continue
        adjusted_p = adjusted.get(test.test_id)
        if adjusted_p is None or test.effect is None:
            warnings.add("TEST_RESULT_INCOMPLETE")
            decisive_inconclusive |= test.decisive
            continue
        observed_direction = 1 if test.effect > 0 else (-1 if test.effect < 0 else 0)
        expected_direction = 1 if test.prediction == "positive" else -1
        effect_large_enough = abs(test.effect) >= test.minimum_effect
        if adjusted_p <= alpha and effect_large_enough and observed_direction == -expected_direction:
            failures.add("DECISIVE_MECHANISM_CONTRADICTION" if test.decisive else "ADVISORY_CONTRADICTION")
        elif adjusted_p <= alpha and effect_large_enough and observed_direction == expected_direction:
            support_count += 1
        elif adjusted_p <= alpha and not effect_large_enough:
            warnings.add("SESOI_NOT_MET")
            decisive_inconclusive |= test.decisive
        elif test.decisive:
            decisive_inconclusive = True
    if "DECISIVE_MECHANISM_CONTRADICTION" in failures:
        outcome: EvidenceOutcome = "falsified"
        cap = None
    elif decisive_inconclusive or decisive_count == 0:
        outcome = "inconclusive"
        cap = "RESEARCH_ONLY" if decisive_inconclusive else None
    elif support_count == len(tests):
        outcome = "supported"
        cap = None
    elif support_count:
        outcome = "partial_support"
        cap = None
    else:
        outcome = "inconclusive"
        cap = "RESEARCH_ONLY"
    return FixedFamilyResult(
        "fixed_falsification_result.v1", outcome, cap,
        tuple(sorted(adjusted.items())), tuple(equivalence),
        tuple(sorted(warnings)), tuple(sorted(failures)), multiplicity_method,
    )


def classify(
    *, support_p: float | None, contradiction_p: float | None,
    lower_p: float | None, upper_p: float | None, alpha: float,
    effective_n: int, min_effective_n: int, negative_control_available: bool,
) -> FixedFamilyResult:
    """Compatibility adapter backed by the closed fixed-family executor."""
    tests: list[FixedTestEvidence] = []
    if not negative_control_available:
        tests.append(FixedTestEvidence("negative_control", "positive", True, effective_n, min_effective_n, available=False, unavailability_code="NEGATIVE_CONTROL_UNAVAILABLE"))
    elif contradiction_p is not None:
        tests.append(FixedTestEvidence("contradiction", "positive", True, effective_n, min_effective_n, contradiction_p, -1.0))
    elif lower_p is not None or upper_p is not None:
        tests.append(FixedTestEvidence("equivalence", "equivalent", True, effective_n, min_effective_n, lower_tost_p=lower_p, upper_tost_p=upper_p))
    else:
        tests.append(FixedTestEvidence("support", "positive", True, effective_n, min_effective_n, support_p, 1.0 if support_p is not None else None))
    return execute_fixed_family(tests, alpha=alpha)


__all__ = ["EvidenceOutcome", "FixedFamilyResult", "FixedHorizonExecutor", "FixedTestEvidence", "classify", "execute_fixed_family"]
