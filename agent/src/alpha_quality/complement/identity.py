"""Separate formula/spec/sign and empirical duplicate identity evidence."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Sequence, cast

import pandas as pd

from src.alpha_quality.complement.model import (
    ComplementPolicy,
    CorrelationEvidence,
    DuplicateIdentityEvidence,
)
from src.research_ledger.hash_utils import canonical_json_hash


@dataclass(frozen=True)
class FactorIdentityRecord:
    factor_spec_id: str
    expression_id: str
    formula_hash: str
    sign_normalized_id: str


def _unavailable(dimension: str, reason: str) -> CorrelationEvidence:
    return CorrelationEvidence(
        dimension=dimension,  # type: ignore[arg-type]
        availability="unavailable",
        maximum_absolute_correlation=None,
        nearest_factor_spec_id=None,
        effective_observations=0,
        reason_code=reason,
    )


def _insufficient(dimension: str, reason: str) -> CorrelationEvidence:
    return CorrelationEvidence(
        dimension=dimension,  # type: ignore[arg-type]
        availability="insufficient",
        maximum_absolute_correlation=None,
        nearest_factor_spec_id=None,
        effective_observations=0,
        reason_code=reason,
    )


def _panel_rank_correlation(
    left: pd.DataFrame,
    right: pd.DataFrame,
    *,
    minimum_cross_section: int,
) -> tuple[float, int] | None:
    dates = left.index.intersection(right.index)
    correlations: list[float] = []
    for date in dates:
        left_row = cast(pd.Series, left.loc[date])
        right_row = cast(pd.Series, right.loc[date])
        symbols = left_row.index.intersection(right_row.index)
        paired = pd.concat(
            [left_row.loc[symbols].rename("candidate"), right_row.loc[symbols].rename("reference")],
            axis=1,
        ).dropna()
        if len(paired) < minimum_cross_section:
            continue
        candidate_rank = cast(pd.Series, paired["candidate"].rank(method="average"))
        reference_rank = cast(pd.Series, paired["reference"].rank(method="average"))
        if candidate_rank.nunique() <= 1 or reference_rank.nunique() <= 1:
            continue
        correlation = candidate_rank.corr(reference_rank)
        if pd.notna(correlation) and math.isfinite(float(correlation)):
            correlations.append(float(correlation))
    if not correlations:
        return None
    return float(sum(correlations) / len(correlations)), len(correlations)


def _maximum_panel_correlation(
    candidate: pd.DataFrame | None,
    references: Mapping[str, pd.DataFrame] | None,
    *,
    minimum_cross_section: int,
) -> CorrelationEvidence:
    if candidate is None or references is None:
        return _unavailable("factor_panel_rank", "PANEL_IDENTITY_EVIDENCE_MISSING")
    if not references:
        return _unavailable("factor_panel_rank", "PANEL_REFERENCE_POOL_EMPTY")
    comparable: list[tuple[float, str, int]] = []
    for factor_spec_id, panel in sorted(references.items()):
        result = _panel_rank_correlation(
            candidate,
            panel,
            minimum_cross_section=minimum_cross_section,
        )
        if result is not None:
            signed, effective = result
            comparable.append((abs(signed), factor_spec_id, effective))
    if not comparable:
        return _insufficient("factor_panel_rank", "PANEL_CORRELATION_INSUFFICIENT")
    maximum, nearest, effective = max(comparable, key=lambda item: (item[0], item[1]))
    return CorrelationEvidence(
        dimension="factor_panel_rank",
        availability="available",
        maximum_absolute_correlation=maximum,
        nearest_factor_spec_id=nearest,
        effective_observations=effective,
        reason_code=None,
    )


def _series_correlation(
    dimension: str,
    candidate: pd.Series | None,
    references: Mapping[str, pd.Series] | None,
    *,
    minimum_observations: int,
) -> CorrelationEvidence:
    if candidate is None or references is None:
        return _unavailable(dimension, f"{dimension.upper()}_IDENTITY_EVIDENCE_MISSING")
    if not references:
        return _unavailable(dimension, f"{dimension.upper()}_REFERENCE_POOL_EMPTY")
    comparable: list[tuple[float, str, int]] = []
    for factor_spec_id, series in sorted(references.items()):
        aligned = pd.concat(
            [candidate.rename("candidate"), series.rename("reference")],
            axis=1,
            join="inner",
        ).dropna()
        if len(aligned) < minimum_observations:
            continue
        correlation = aligned["candidate"].corr(aligned["reference"])
        if pd.notna(correlation) and math.isfinite(float(correlation)):
            comparable.append((abs(float(correlation)), factor_spec_id, len(aligned)))
    if not comparable:
        return _insufficient(dimension, f"{dimension.upper()}_CORRELATION_INSUFFICIENT")
    maximum, nearest, effective = max(comparable, key=lambda item: (item[0], item[1]))
    return CorrelationEvidence(
        dimension=dimension,  # type: ignore[arg-type]
        availability="available",
        maximum_absolute_correlation=maximum,
        nearest_factor_spec_id=nearest,
        effective_observations=effective,
        reason_code=None,
    )


def build_duplicate_identity_evidence(
    candidate: FactorIdentityRecord,
    existing_identities: Sequence[FactorIdentityRecord],
    *,
    candidate_panel: pd.DataFrame | None,
    existing_panels: Mapping[str, pd.DataFrame] | None,
    candidate_ic_series: pd.Series | None,
    existing_ic_series: Mapping[str, pd.Series] | None,
    candidate_net_returns: pd.Series | None,
    existing_net_returns: Mapping[str, pd.Series] | None,
    policy: ComplementPolicy,
    polarity_control: bool = False,
) -> DuplicateIdentityEvidence:
    exact_expression = tuple(sorted(record.factor_spec_id for record in existing_identities if record.expression_id == candidate.expression_id))
    exact_spec = tuple(sorted(record.factor_spec_id for record in existing_identities if record.factor_spec_id == candidate.factor_spec_id))
    exact_formula = tuple(sorted(record.factor_spec_id for record in existing_identities if record.formula_hash == candidate.formula_hash))
    sign_matches = tuple(sorted(record.factor_spec_id for record in existing_identities if record.sign_normalized_id == candidate.sign_normalized_id))

    panel = _maximum_panel_correlation(
        candidate_panel,
        existing_panels,
        minimum_cross_section=policy.minimum_cross_section,
    )
    ic = _series_correlation(
        "ic_series",
        candidate_ic_series,
        existing_ic_series,
        minimum_observations=policy.minimum_effective_dates,
    )
    returns = _series_correlation(
        "net_return",
        candidate_net_returns,
        existing_net_returns,
        minimum_observations=policy.minimum_effective_dates,
    )
    reasons: set[str] = set()
    if exact_spec:
        reasons.add("EXACT_FACTOR_SPEC_DUPLICATE")
    if exact_expression:
        reasons.add("EXACT_EXPRESSION_DUPLICATE")
    if exact_formula:
        reasons.add("EXACT_FORMULA_DUPLICATE")
    if sign_matches and not polarity_control:
        reasons.add("SIGN_NORMALIZED_DUPLICATE")
    for evidence, threshold, reason in (
        (panel, policy.panel_duplicate_threshold, "PANEL_ABSOLUTE_CORRELATION_DUPLICATE"),
        (ic, policy.ic_duplicate_threshold, "IC_ABSOLUTE_CORRELATION_DUPLICATE"),
        (returns, policy.return_duplicate_threshold, "RETURN_ABSOLUTE_CORRELATION_DUPLICATE"),
    ):
        if (
            evidence.availability == "available"
            and evidence.maximum_absolute_correlation is not None
            and evidence.maximum_absolute_correlation >= threshold
        ):
            reasons.add(reason)
    content: dict[str, object] = {
        "schema_version": "duplicate_identity_evidence.v2",
        "factor_spec_id": candidate.factor_spec_id,
        "expression_id": candidate.expression_id,
        "formula_hash": candidate.formula_hash,
        "sign_normalized_id": candidate.sign_normalized_id,
        "polarity_control": polarity_control,
        "exact_expression_matches": list(exact_expression),
        "exact_factor_spec_matches": list(exact_spec),
        "exact_formula_matches": list(exact_formula),
        "sign_normalized_matches": list(sign_matches),
        "panel_correlation": panel.to_dict(),
        "ic_correlation": ic.to_dict(),
        "return_correlation": returns.to_dict(),
        "duplicate_detected": bool(reasons),
        "duplicate_reasons": sorted(reasons),
    }
    return DuplicateIdentityEvidence(
        schema_version="duplicate_identity_evidence.v2",
        factor_spec_id=candidate.factor_spec_id,
        expression_id=candidate.expression_id,
        formula_hash=candidate.formula_hash,
        sign_normalized_id=candidate.sign_normalized_id,
        polarity_control=polarity_control,
        exact_expression_matches=exact_expression,
        exact_factor_spec_matches=exact_spec,
        exact_formula_matches=exact_formula,
        sign_normalized_matches=sign_matches,
        panel_correlation=panel,
        ic_correlation=ic,
        return_correlation=returns,
        duplicate_detected=bool(reasons),
        duplicate_reasons=tuple(sorted(reasons)),
        identity_hash=canonical_json_hash(content),
    )


__all__ = ["FactorIdentityRecord", "build_duplicate_identity_evidence"]
