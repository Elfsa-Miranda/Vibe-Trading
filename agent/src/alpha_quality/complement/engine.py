"""Deterministic ComplementEvidence.v2 production builder."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping, Sequence

import pandas as pd

from src.alpha_quality.complement.identity import (
    FactorIdentityRecord,
    build_duplicate_identity_evidence,
)
from src.alpha_quality.complement.model import ComplementEvidenceV2, ComplementPolicy
from src.alpha_quality.complement.portfolio import compute_portfolio_complement
from src.alpha_quality.complement.residual import compute_residual_complement
from src.alpha_quality.flags import ResolvedAGSFlags
from src.research_ledger.hash_utils import canonical_json_hash


@dataclass(frozen=True)
class ComplementInputs:
    snapshot_hash: str
    data_scope: Literal["train_valid", "valid"]
    candidate_identity: FactorIdentityRecord
    existing_identities: Sequence[FactorIdentityRecord]
    candidate_panel: pd.DataFrame | None
    existing_panels: Mapping[str, pd.DataFrame] | None
    candidate_ic_series: pd.Series | None
    existing_ic_series: Mapping[str, pd.Series] | None
    candidate_net_returns: pd.Series | None
    existing_net_returns: Mapping[str, pd.Series] | None
    forward_returns: pd.DataFrame | None
    valid_mask: pd.DataFrame | None
    pool_net_returns: pd.Series | None
    candidate_gross_returns: pd.Series | None
    pool_turnover: pd.Series | None
    candidate_turnover: pd.Series | None
    candidate_cost_bps: pd.Series | None
    candidate_capacity_scale: pd.Series | None
    candidate_exposure_penalty: pd.Series | None
    semantic_similarity: float | None = None
    structural_similarity: float | None = None
    polarity_control: bool = False

    def __post_init__(self) -> None:
        if self.data_scope not in {"train_valid", "valid"}:
            raise ValueError("complement inputs are train/valid only")


class ComplementEngine:
    def __init__(self, *, flags: ResolvedAGSFlags, policy: ComplementPolicy) -> None:
        if not flags.enabled("VIBE_TRADING_COMPLEMENT_V2"):
            raise RuntimeError("ComplementEvidence.v2 capability is disabled")
        self.policy = policy

    def evaluate(self, inputs: ComplementInputs) -> ComplementEvidenceV2:
        if inputs.data_scope != self.policy.data_scope:
            raise ValueError("complement input scope does not match frozen policy")
        identity = build_duplicate_identity_evidence(
            inputs.candidate_identity,
            inputs.existing_identities,
            candidate_panel=inputs.candidate_panel,
            existing_panels=inputs.existing_panels,
            candidate_ic_series=inputs.candidate_ic_series,
            existing_ic_series=inputs.existing_ic_series,
            candidate_net_returns=inputs.candidate_net_returns,
            existing_net_returns=inputs.existing_net_returns,
            policy=self.policy,
            polarity_control=inputs.polarity_control,
        )
        residual = compute_residual_complement(
            candidate_panel=inputs.candidate_panel,
            reference_panels=inputs.existing_panels,
            forward_returns=inputs.forward_returns,
            valid_mask=inputs.valid_mask,
            policy=self.policy,
        )
        portfolio = compute_portfolio_complement(
            pool_net_returns=inputs.pool_net_returns,
            candidate_gross_returns=inputs.candidate_gross_returns,
            pool_turnover=inputs.pool_turnover,
            candidate_turnover=inputs.candidate_turnover,
            candidate_cost_bps=inputs.candidate_cost_bps,
            candidate_capacity_scale=inputs.candidate_capacity_scale,
            candidate_exposure_penalty=inputs.candidate_exposure_penalty,
            policy=self.policy,
        )
        reasons: set[str] = set()
        warnings: set[str] = set()
        limitations: set[str] = {"TRAIN_VALID_EVIDENCE_ONLY"}
        correlation_availability = (
            identity.panel_correlation.availability,
            identity.ic_correlation.availability,
            identity.return_correlation.availability,
        )
        missing_reasons = {
            evidence.reason_code
            for evidence in (
                identity.panel_correlation,
                identity.ic_correlation,
                identity.return_correlation,
            )
            if evidence.reason_code is not None
        }
        if identity.duplicate_detected:
            status = "duplicate"
            cap = None
            reasons.update(identity.duplicate_reasons)
        elif "unavailable" in correlation_availability or residual.availability == "unavailable" or portfolio.availability == "unavailable":
            status = "unavailable"
            cap = "RESEARCH_ONLY"
            reasons.add("COMPLEMENT_REQUIRED_EVIDENCE_UNAVAILABLE")
            reasons.update(missing_reasons)
            if residual.reason_code:
                reasons.add(residual.reason_code)
            if portfolio.reason_code:
                reasons.add(portfolio.reason_code)
        elif "insufficient" in correlation_availability or residual.availability == "insufficient" or portfolio.availability == "insufficient":
            status = "insufficient"
            cap = "RESEARCH_ONLY"
            reasons.add("COMPLEMENT_SAMPLE_INSUFFICIENT")
            reasons.update(missing_reasons)
            if residual.reason_code:
                reasons.add(residual.reason_code)
            if portfolio.reason_code:
                reasons.add(portfolio.reason_code)
        elif (
            portfolio.delta_information_ratio is None
            or portfolio.delta_net_return_mean is None
            or portfolio.delta_information_ratio <= 0.0
            or portfolio.delta_net_return_mean <= 0.0
        ):
            status = "nonpositive_marginal_value"
            cap = None
            reasons.add("NET_MARGINAL_VALUE_NONPOSITIVE")
        else:
            status = "complementary"
            cap = None
            reasons.add("NET_MARGINAL_VALUE_POSITIVE")
        if residual.availability == "available" and residual.rank_ic_mean is not None and residual.rank_ic_mean <= 0.0:
            warnings.add("RESIDUAL_IC_NONPOSITIVE")
        if inputs.semantic_similarity is not None:
            warnings.add("SEMANTIC_SIMILARITY_ADVISORY_ONLY")
        if inputs.structural_similarity is not None:
            warnings.add("STRUCTURAL_SIMILARITY_ADVISORY_ONLY")
        content: dict[str, object] = {
            "schema_version": "complement_evidence.v2",
            "factor_spec_id": inputs.candidate_identity.factor_spec_id,
            "data_scope": inputs.data_scope,
            "snapshot_hash": inputs.snapshot_hash,
            "policy_version": self.policy.policy_version,
            "policy_hash": self.policy.policy_hash,
            "identity": identity.to_dict(),
            "residual": residual.to_dict(),
            "portfolio": portfolio.to_dict(),
            "semantic_similarity": inputs.semantic_similarity,
            "structural_similarity": inputs.structural_similarity,
            "status": status,
            "cap": cap,
            "reason_codes": sorted(reasons),
            "warning_codes": sorted(warnings),
            "limitation_codes": sorted(limitations),
        }
        return ComplementEvidenceV2(
            schema_version="complement_evidence.v2",
            factor_spec_id=inputs.candidate_identity.factor_spec_id,
            data_scope=inputs.data_scope,
            snapshot_hash=inputs.snapshot_hash,
            policy_version=self.policy.policy_version,
            policy_hash=self.policy.policy_hash,
            identity=identity,
            residual=residual,
            portfolio=portfolio,
            semantic_similarity=inputs.semantic_similarity,
            structural_similarity=inputs.structural_similarity,
            status=status,  # type: ignore[arg-type]
            cap=cap,  # type: ignore[arg-type]
            reason_codes=tuple(sorted(reasons)),
            warning_codes=tuple(sorted(warnings)),
            limitation_codes=tuple(sorted(limitations)),
            complement_hash=canonical_json_hash(content),
        )


__all__ = ["ComplementEngine", "ComplementInputs"]
