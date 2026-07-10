"""Immutable, scope-bound ComplementEvidence.v2 models."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Literal

from src.research_ledger.hash_utils import canonical_json_hash

_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

Availability = Literal["available", "insufficient", "unavailable"]
ComplementStatus = Literal[
    "duplicate",
    "unavailable",
    "insufficient",
    "nonpositive_marginal_value",
    "complementary",
]


def _require_hash(value: str, name: str) -> None:
    if not isinstance(value, str) or _HASH_RE.fullmatch(value) is None:
        raise ValueError(f"{name} must be a canonical sha256 hash")


def _require_text(value: str, name: str, *, maximum: int = 256) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{name} must be bounded non-empty text")


def _finite_optional(value: float | None, name: str) -> None:
    if value is not None and not math.isfinite(value):
        raise ValueError(f"{name} must be finite when present")


def _codes(values: tuple[str, ...], name: str) -> tuple[str, ...]:
    normalized = tuple(sorted(set(values)))
    if normalized != values or any(not value or len(value) > 128 for value in values):
        raise ValueError(f"{name} must be sorted, unique, bounded codes")
    return normalized


@dataclass(frozen=True)
class ComplementPolicy:
    schema_version: Literal["complement_policy.v2"]
    policy_version: str
    data_scope: Literal["train_valid", "valid"]
    panel_duplicate_threshold: float
    ic_duplicate_threshold: float
    return_duplicate_threshold: float
    ridge_alpha: float
    minimum_cross_section: int
    minimum_effective_dates: int
    candidate_allocation: float
    annualization_factor: int
    bootstrap_samples: int
    bootstrap_block_length: int
    bootstrap_seed: int
    require_execution_evidence: bool
    require_capacity_evidence: bool
    require_exposure_evidence: bool
    portfolio_construction_hash: str
    cost_model_hash: str
    capacity_model_hash: str
    exposure_model_hash: str

    def __post_init__(self) -> None:
        if self.schema_version != "complement_policy.v2":
            raise ValueError("unsupported complement policy schema")
        _require_text(self.policy_version, "policy_version")
        if self.data_scope not in {"train_valid", "valid"}:
            raise ValueError("complement policy is train/valid only")
        thresholds = (
            self.panel_duplicate_threshold,
            self.ic_duplicate_threshold,
            self.return_duplicate_threshold,
        )
        if any(not math.isfinite(value) or not 0.0 <= value <= 1.0 for value in thresholds):
            raise ValueError("duplicate thresholds must be finite and in [0, 1]")
        if not math.isfinite(self.ridge_alpha) or self.ridge_alpha <= 0.0:
            raise ValueError("ridge_alpha must be finite and positive")
        for name in (
            "minimum_cross_section",
            "minimum_effective_dates",
            "annualization_factor",
            "bootstrap_samples",
            "bootstrap_block_length",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.bootstrap_samples > 10_000:
            raise ValueError("bootstrap_samples exceeds resource limit")
        if not math.isfinite(self.candidate_allocation) or not 0.0 < self.candidate_allocation <= 1.0:
            raise ValueError("candidate_allocation must be in (0, 1]")
        if isinstance(self.bootstrap_seed, bool) or not isinstance(self.bootstrap_seed, int):
            raise ValueError("bootstrap_seed must be an integer")
        for name in (
            "portfolio_construction_hash",
            "cost_model_hash",
            "capacity_model_hash",
            "exposure_model_hash",
        ):
            _require_hash(getattr(self, name), name)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "policy_version": self.policy_version,
            "data_scope": self.data_scope,
            "panel_duplicate_threshold": self.panel_duplicate_threshold,
            "ic_duplicate_threshold": self.ic_duplicate_threshold,
            "return_duplicate_threshold": self.return_duplicate_threshold,
            "ridge_alpha": self.ridge_alpha,
            "minimum_cross_section": self.minimum_cross_section,
            "minimum_effective_dates": self.minimum_effective_dates,
            "candidate_allocation": self.candidate_allocation,
            "annualization_factor": self.annualization_factor,
            "bootstrap_samples": self.bootstrap_samples,
            "bootstrap_block_length": self.bootstrap_block_length,
            "bootstrap_seed": self.bootstrap_seed,
            "require_execution_evidence": self.require_execution_evidence,
            "require_capacity_evidence": self.require_capacity_evidence,
            "require_exposure_evidence": self.require_exposure_evidence,
            "portfolio_construction_hash": self.portfolio_construction_hash,
            "cost_model_hash": self.cost_model_hash,
            "capacity_model_hash": self.capacity_model_hash,
            "exposure_model_hash": self.exposure_model_hash,
        }

    @property
    def policy_hash(self) -> str:
        return canonical_json_hash(self.to_dict())


@dataclass(frozen=True)
class CorrelationEvidence:
    dimension: Literal["factor_panel_rank", "ic_series", "net_return"]
    availability: Availability
    maximum_absolute_correlation: float | None
    nearest_factor_spec_id: str | None
    effective_observations: int
    reason_code: str | None

    def __post_init__(self) -> None:
        if self.dimension not in {"factor_panel_rank", "ic_series", "net_return"}:
            raise ValueError("unknown correlation evidence dimension")
        if self.availability not in {"available", "insufficient", "unavailable"}:
            raise ValueError("unknown correlation evidence availability")
        if isinstance(self.effective_observations, bool) or self.effective_observations < 0:
            raise ValueError("effective_observations must be non-negative")
        if self.availability == "available":
            if (
                self.maximum_absolute_correlation is None
                or not math.isfinite(self.maximum_absolute_correlation)
                or not 0.0 <= self.maximum_absolute_correlation <= 1.0
                or not self.nearest_factor_spec_id
                or self.reason_code is not None
            ):
                raise ValueError("available correlation evidence is incomplete")
        elif (
            self.maximum_absolute_correlation is not None
            or self.nearest_factor_spec_id is not None
            or not self.reason_code
        ):
            raise ValueError("unavailable correlation evidence cannot carry a value")

    def to_dict(self) -> dict[str, object]:
        return {
            "dimension": self.dimension,
            "availability": self.availability,
            "maximum_absolute_correlation": self.maximum_absolute_correlation,
            "nearest_factor_spec_id": self.nearest_factor_spec_id,
            "effective_observations": self.effective_observations,
            "reason_code": self.reason_code,
        }


@dataclass(frozen=True)
class DuplicateIdentityEvidence:
    schema_version: Literal["duplicate_identity_evidence.v2"]
    factor_spec_id: str
    expression_id: str
    formula_hash: str
    sign_normalized_id: str
    polarity_control: bool
    exact_expression_matches: tuple[str, ...]
    exact_factor_spec_matches: tuple[str, ...]
    exact_formula_matches: tuple[str, ...]
    sign_normalized_matches: tuple[str, ...]
    panel_correlation: CorrelationEvidence
    ic_correlation: CorrelationEvidence
    return_correlation: CorrelationEvidence
    duplicate_detected: bool
    duplicate_reasons: tuple[str, ...]
    identity_hash: str

    def __post_init__(self) -> None:
        if self.schema_version != "duplicate_identity_evidence.v2":
            raise ValueError("unsupported identity evidence schema")
        _require_text(self.factor_spec_id, "factor_spec_id")
        for name in ("expression_id", "formula_hash", "sign_normalized_id"):
            _require_hash(getattr(self, name), name)
        for name in (
            "exact_expression_matches",
            "exact_factor_spec_matches",
            "exact_formula_matches",
            "sign_normalized_matches",
        ):
            values = getattr(self, name)
            if values != tuple(sorted(set(values))):
                raise ValueError(f"{name} must be sorted and unique")
        _codes(self.duplicate_reasons, "duplicate_reasons")
        if self.duplicate_detected != bool(self.duplicate_reasons):
            raise ValueError("duplicate marker and reasons disagree")
        _require_hash(self.identity_hash, "identity_hash")
        if self.identity_hash != canonical_json_hash(self._content_dict()):
            raise ValueError("identity_hash does not match content")

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "factor_spec_id": self.factor_spec_id,
            "expression_id": self.expression_id,
            "formula_hash": self.formula_hash,
            "sign_normalized_id": self.sign_normalized_id,
            "polarity_control": self.polarity_control,
            "exact_expression_matches": list(self.exact_expression_matches),
            "exact_factor_spec_matches": list(self.exact_factor_spec_matches),
            "exact_formula_matches": list(self.exact_formula_matches),
            "sign_normalized_matches": list(self.sign_normalized_matches),
            "panel_correlation": self.panel_correlation.to_dict(),
            "ic_correlation": self.ic_correlation.to_dict(),
            "return_correlation": self.return_correlation.to_dict(),
            "duplicate_detected": self.duplicate_detected,
            "duplicate_reasons": list(self.duplicate_reasons),
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._content_dict(), "identity_hash": self.identity_hash}


@dataclass(frozen=True)
class ResidualComplementEvidence:
    schema_version: Literal["residual_complement_evidence.v2"]
    availability: Availability
    ridge_alpha: float
    solver: Literal["date_wise_ridge", "not_run"]
    effective_dates: int
    rank_ic_mean: float | None
    rank_ic_std: float | None
    rank_icir: float | None
    t_stat: float | None
    uncertainty_method: str | None
    reason_code: str | None
    evidence_hash: str

    def __post_init__(self) -> None:
        if self.schema_version != "residual_complement_evidence.v2":
            raise ValueError("unsupported residual evidence schema")
        if not math.isfinite(self.ridge_alpha) or self.ridge_alpha <= 0.0:
            raise ValueError("ridge_alpha must be positive")
        if self.effective_dates < 0:
            raise ValueError("effective_dates must be non-negative")
        for name in ("rank_ic_mean", "rank_ic_std", "rank_icir", "t_stat"):
            _finite_optional(getattr(self, name), name)
        metrics = (self.rank_ic_mean, self.rank_ic_std, self.rank_icir, self.t_stat)
        if self.availability == "available":
            if any(value is None for value in metrics) or self.solver != "date_wise_ridge" or self.reason_code is not None:
                raise ValueError("available residual evidence is incomplete")
        elif any(value is not None for value in metrics) or not self.reason_code or self.solver != "not_run":
            raise ValueError("unavailable residual evidence cannot carry metrics")
        _require_hash(self.evidence_hash, "evidence_hash")
        if self.evidence_hash != canonical_json_hash(self._content_dict()):
            raise ValueError("residual evidence hash mismatch")

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "availability": self.availability,
            "ridge_alpha": self.ridge_alpha,
            "solver": self.solver,
            "effective_dates": self.effective_dates,
            "rank_ic_mean": self.rank_ic_mean,
            "rank_ic_std": self.rank_ic_std,
            "rank_icir": self.rank_icir,
            "t_stat": self.t_stat,
            "uncertainty_method": self.uncertainty_method,
            "reason_code": self.reason_code,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._content_dict(), "evidence_hash": self.evidence_hash}


@dataclass(frozen=True)
class PortfolioComplementEvidence:
    schema_version: Literal["portfolio_complement_evidence.v2"]
    availability: Availability
    effective_dates: int
    candidate_allocation: float
    net_return_mean_before: float | None
    net_return_mean_after: float | None
    delta_net_return_mean: float | None
    information_ratio_before: float | None
    information_ratio_after: float | None
    delta_information_ratio: float | None
    max_drawdown_before: float | None
    max_drawdown_after: float | None
    delta_max_drawdown: float | None
    turnover_before: float | None
    turnover_after: float | None
    delta_turnover: float | None
    candidate_cost_bps_mean: float | None
    candidate_capacity_scale_mean: float | None
    candidate_exposure_penalty_mean: float | None
    delta_ir_interval: tuple[float, float] | None
    uncertainty_method: str | None
    reason_code: str | None
    evidence_hash: str

    def __post_init__(self) -> None:
        if self.schema_version != "portfolio_complement_evidence.v2":
            raise ValueError("unsupported portfolio evidence schema")
        if self.effective_dates < 0 or not 0.0 < self.candidate_allocation <= 1.0:
            raise ValueError("invalid portfolio evidence count or allocation")
        metric_names = (
            "net_return_mean_before", "net_return_mean_after", "delta_net_return_mean",
            "information_ratio_before", "information_ratio_after", "delta_information_ratio",
            "max_drawdown_before", "max_drawdown_after", "delta_max_drawdown",
            "turnover_before", "turnover_after", "delta_turnover",
            "candidate_cost_bps_mean", "candidate_capacity_scale_mean",
            "candidate_exposure_penalty_mean",
        )
        metrics = tuple(getattr(self, name) for name in metric_names)
        for name, value in zip(metric_names, metrics, strict=True):
            _finite_optional(value, name)
        if self.availability == "available":
            if any(value is None for value in metrics) or self.delta_ir_interval is None or self.reason_code is not None:
                raise ValueError("available portfolio evidence is incomplete")
            if any(not math.isfinite(value) for value in self.delta_ir_interval):
                raise ValueError("delta IR interval must be finite")
        elif any(value is not None for value in metrics) or self.delta_ir_interval is not None or not self.reason_code:
            raise ValueError("unavailable portfolio evidence cannot carry metrics")
        _require_hash(self.evidence_hash, "evidence_hash")
        if self.evidence_hash != canonical_json_hash(self._content_dict()):
            raise ValueError("portfolio evidence hash mismatch")

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "availability": self.availability,
            "effective_dates": self.effective_dates,
            "candidate_allocation": self.candidate_allocation,
            "net_return_mean_before": self.net_return_mean_before,
            "net_return_mean_after": self.net_return_mean_after,
            "delta_net_return_mean": self.delta_net_return_mean,
            "information_ratio_before": self.information_ratio_before,
            "information_ratio_after": self.information_ratio_after,
            "delta_information_ratio": self.delta_information_ratio,
            "max_drawdown_before": self.max_drawdown_before,
            "max_drawdown_after": self.max_drawdown_after,
            "delta_max_drawdown": self.delta_max_drawdown,
            "turnover_before": self.turnover_before,
            "turnover_after": self.turnover_after,
            "delta_turnover": self.delta_turnover,
            "candidate_cost_bps_mean": self.candidate_cost_bps_mean,
            "candidate_capacity_scale_mean": self.candidate_capacity_scale_mean,
            "candidate_exposure_penalty_mean": self.candidate_exposure_penalty_mean,
            "delta_ir_interval": None if self.delta_ir_interval is None else list(self.delta_ir_interval),
            "uncertainty_method": self.uncertainty_method,
            "reason_code": self.reason_code,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._content_dict(), "evidence_hash": self.evidence_hash}


@dataclass(frozen=True)
class ComplementEvidenceV2:
    schema_version: Literal["complement_evidence.v2"]
    factor_spec_id: str
    data_scope: Literal["train_valid", "valid"]
    snapshot_hash: str
    policy_version: str
    policy_hash: str
    identity: DuplicateIdentityEvidence
    residual: ResidualComplementEvidence
    portfolio: PortfolioComplementEvidence
    semantic_similarity: float | None
    structural_similarity: float | None
    status: ComplementStatus
    cap: Literal["RESEARCH_ONLY"] | None
    reason_codes: tuple[str, ...]
    warning_codes: tuple[str, ...]
    limitation_codes: tuple[str, ...]
    complement_hash: str

    def __post_init__(self) -> None:
        if self.schema_version != "complement_evidence.v2":
            raise ValueError("unsupported complement evidence schema")
        _require_text(self.factor_spec_id, "factor_spec_id")
        _require_hash(self.snapshot_hash, "snapshot_hash")
        _require_text(self.policy_version, "policy_version")
        _require_hash(self.policy_hash, "policy_hash")
        if self.identity.factor_spec_id != self.factor_spec_id:
            raise ValueError("identity factor does not match complement evidence")
        for name in ("semantic_similarity", "structural_similarity"):
            value = getattr(self, name)
            if value is not None and (not math.isfinite(value) or not 0.0 <= value <= 1.0):
                raise ValueError(f"{name} must be advisory in [0, 1]")
        _codes(self.reason_codes, "reason_codes")
        _codes(self.warning_codes, "warning_codes")
        _codes(self.limitation_codes, "limitation_codes")
        if self.status in {"unavailable", "insufficient"} and self.cap != "RESEARCH_ONLY":
            raise ValueError("missing complement evidence must cap research_only")
        if self.status not in {"unavailable", "insufficient"} and self.cap is not None:
            raise ValueError("complete complement evidence cannot carry a missing-evidence cap")
        _require_hash(self.complement_hash, "complement_hash")
        if self.complement_hash != canonical_json_hash(self._content_dict()):
            raise ValueError("complement_hash does not match content")

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "factor_spec_id": self.factor_spec_id,
            "data_scope": self.data_scope,
            "snapshot_hash": self.snapshot_hash,
            "policy_version": self.policy_version,
            "policy_hash": self.policy_hash,
            "identity": self.identity.to_dict(),
            "residual": self.residual.to_dict(),
            "portfolio": self.portfolio.to_dict(),
            "semantic_similarity": self.semantic_similarity,
            "structural_similarity": self.structural_similarity,
            "status": self.status,
            "cap": self.cap,
            "reason_codes": list(self.reason_codes),
            "warning_codes": list(self.warning_codes),
            "limitation_codes": list(self.limitation_codes),
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._content_dict(), "complement_hash": self.complement_hash}


__all__ = [
    "Availability",
    "ComplementEvidenceV2",
    "ComplementPolicy",
    "ComplementStatus",
    "CorrelationEvidence",
    "DuplicateIdentityEvidence",
    "PortfolioComplementEvidence",
    "ResidualComplementEvidence",
]
