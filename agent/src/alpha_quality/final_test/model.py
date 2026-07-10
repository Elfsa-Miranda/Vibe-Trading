"""Frozen final-test configuration, data, artifact, and decision-only view."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from src.alpha_quality.decision_v2.model import DecisionEvidenceRecord
from src.research_ledger.hash_utils import canonical_json_hash

_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")


def _hash(value: str, name: str) -> None:
    if not isinstance(value, str) or _HASH_RE.fullmatch(value) is None:
        raise ValueError(f"{name} must be a canonical sha256 hash")


def _timestamp(value: str, name: str) -> None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{name} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{name} must include timezone")


def _date(value: str, name: str) -> None:
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an ISO date") from exc


def _limitations(values: tuple[str, ...], name: str) -> None:
    if values != tuple(sorted(set(values))) or any(
        _CODE_RE.fullmatch(value) is None for value in values
    ):
        raise ValueError(f"{name} must be sorted unique safe codes")


@dataclass(frozen=True)
class FinalTestPolicy:
    schema_version: Literal["final_test_policy.v1"]
    policy_version: str
    minimum_effective_observations: int
    minimum_rank_ic_mean: float
    minimum_net_return_mean: float

    def __post_init__(self) -> None:
        if self.schema_version != "final_test_policy.v1":
            raise ValueError("unsupported final-test policy schema")
        if not self.policy_version or self.minimum_effective_observations < 2:
            raise ValueError("invalid final-test policy identity or sample floor")
        if not all(
            math.isfinite(value)
            for value in (self.minimum_rank_ic_mean, self.minimum_net_return_mean)
        ):
            raise ValueError("final-test thresholds must be finite")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "policy_version": self.policy_version,
            "minimum_effective_observations": self.minimum_effective_observations,
            "minimum_rank_ic_mean": self.minimum_rank_ic_mean,
            "minimum_net_return_mean": self.minimum_net_return_mean,
        }

    @property
    def policy_hash(self) -> str:
        return canonical_json_hash(self.to_dict())


@dataclass(frozen=True)
class FrozenFinalCandidate:
    schema_version: Literal["frozen_final_candidate.v1"]
    factor_spec_id: str
    definition_hash: str
    transform_pipeline_hash: str
    cost_model_hash: str
    regime_config_hash: str
    policy_hash: str
    data_snapshot_hash: str
    frozen_at: str
    candidate_hash: str

    def __post_init__(self) -> None:
        if self.schema_version != "frozen_final_candidate.v1" or not self.factor_spec_id:
            raise ValueError("invalid frozen candidate schema or identity")
        for name in (
            "definition_hash",
            "transform_pipeline_hash",
            "cost_model_hash",
            "regime_config_hash",
            "policy_hash",
            "data_snapshot_hash",
            "candidate_hash",
        ):
            _hash(getattr(self, name), name)
        _timestamp(self.frozen_at, "frozen_at")
        if self.candidate_hash != canonical_json_hash(self._content_dict()):
            raise ValueError("frozen candidate hash mismatch")

    @classmethod
    def create(
        cls,
        *,
        factor_spec_id: str,
        definition_hash: str,
        transform_pipeline_hash: str,
        cost_model_hash: str,
        regime_config_hash: str,
        policy_hash: str,
        data_snapshot_hash: str,
        frozen_at: str,
    ) -> "FrozenFinalCandidate":
        content = {
            "schema_version": "frozen_final_candidate.v1",
            "factor_spec_id": factor_spec_id,
            "definition_hash": definition_hash,
            "transform_pipeline_hash": transform_pipeline_hash,
            "cost_model_hash": cost_model_hash,
            "regime_config_hash": regime_config_hash,
            "policy_hash": policy_hash,
            "data_snapshot_hash": data_snapshot_hash,
            "frozen_at": frozen_at,
        }
        return cls(
            schema_version="frozen_final_candidate.v1",
            factor_spec_id=factor_spec_id,
            definition_hash=definition_hash,
            transform_pipeline_hash=transform_pipeline_hash,
            cost_model_hash=cost_model_hash,
            regime_config_hash=regime_config_hash,
            policy_hash=policy_hash,
            data_snapshot_hash=data_snapshot_hash,
            frozen_at=frozen_at,
            candidate_hash=canonical_json_hash(content),
        )

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "factor_spec_id": self.factor_spec_id,
            "definition_hash": self.definition_hash,
            "transform_pipeline_hash": self.transform_pipeline_hash,
            "cost_model_hash": self.cost_model_hash,
            "regime_config_hash": self.regime_config_hash,
            "policy_hash": self.policy_hash,
            "data_snapshot_hash": self.data_snapshot_hash,
            "frozen_at": self.frozen_at,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._content_dict(), "candidate_hash": self.candidate_hash}


@dataclass(frozen=True)
class FinalTestDataRequest:
    run_id: str
    factor_spec_id: str
    candidate_hash: str
    data_snapshot_hash: str
    period_start: str
    period_end: str
    fields: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.run_id or not self.factor_spec_id:
            raise ValueError("final request requires run and factor identity")
        _hash(self.candidate_hash, "candidate_hash")
        _hash(self.data_snapshot_hash, "data_snapshot_hash")
        _date(self.period_start, "period_start")
        _date(self.period_end, "period_end")
        if self.period_end < self.period_start:
            raise ValueError("final request period is reversed")
        if self.fields != tuple(sorted(set(self.fields))) or not self.fields:
            raise ValueError("final request fields must be sorted, unique and non-empty")

    @property
    def request_hash(self) -> str:
        return canonical_json_hash(
            {
                "run_id": self.run_id,
                "factor_spec_id": self.factor_spec_id,
                "candidate_hash": self.candidate_hash,
                "data_snapshot_hash": self.data_snapshot_hash,
                "period_start": self.period_start,
                "period_end": self.period_end,
                "fields": list(self.fields),
            }
        )


@dataclass(frozen=True)
class FinalTestDataset:
    data_snapshot_hash: str
    period_start: str
    period_end: str
    rank_ic_series: tuple[float, ...]
    net_returns: tuple[float, ...]
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _hash(self.data_snapshot_hash, "data_snapshot_hash")
        _date(self.period_start, "period_start")
        _date(self.period_end, "period_end")
        if self.period_end < self.period_start:
            raise ValueError("final dataset period is reversed")
        if not self.rank_ic_series or len(self.rank_ic_series) != len(self.net_returns):
            raise ValueError("final dataset series must be non-empty and aligned")
        if any(not math.isfinite(value) for value in (*self.rank_ic_series, *self.net_returns)):
            raise ValueError("final dataset contains non-finite values")
        _limitations(self.limitations, "final dataset limitations")


@dataclass(frozen=True)
class FinalTestAccessAudit:
    access_event_hash: str
    request_hash: str
    outcome: Literal["allowed", "denied"]
    reason_code: str
    contaminated: bool
    accessed_at: str

    def __post_init__(self) -> None:
        _hash(self.access_event_hash, "access_event_hash")
        _hash(self.request_hash, "request_hash")
        _timestamp(self.accessed_at, "accessed_at")
        if _CODE_RE.fullmatch(self.reason_code) is None:
            raise ValueError("final access reason must be a safe code")

    def to_dict(self) -> dict[str, object]:
        return {
            "access_event_hash": self.access_event_hash,
            "request_hash": self.request_hash,
            "outcome": self.outcome,
            "reason_code": self.reason_code,
            "contaminated": self.contaminated,
            "accessed_at": self.accessed_at,
        }


@dataclass(frozen=True)
class FinalTestArtifact:
    schema_version: Literal["final_test_artifact.v1"]
    factor_spec_id: str
    candidate_hash: str
    definition_hash: str
    transform_pipeline_hash: str
    cost_model_hash: str
    regime_config_hash: str
    policy_hash: str
    data_snapshot_hash: str
    data_scope: Literal["test"]
    period_start: str
    period_end: str
    effective_observations: int
    rank_ic_mean: float
    rank_ic_standard_error: float
    net_return_mean: float
    net_return_standard_error: float
    quality_passed: bool
    contaminated: bool
    access_audit: tuple[FinalTestAccessAudit, ...]
    limitations: tuple[str, ...]
    artifact_hash: str

    def __post_init__(self) -> None:
        if self.schema_version != "final_test_artifact.v1" or self.data_scope != "test":
            raise ValueError("unsupported final-test artifact schema or scope")
        for name in (
            "candidate_hash",
            "definition_hash",
            "transform_pipeline_hash",
            "cost_model_hash",
            "regime_config_hash",
            "policy_hash",
            "data_snapshot_hash",
            "artifact_hash",
        ):
            _hash(getattr(self, name), name)
        _date(self.period_start, "period_start")
        _date(self.period_end, "period_end")
        if self.effective_observations < 1 or not all(
            math.isfinite(value)
            for value in (
                self.rank_ic_mean,
                self.rank_ic_standard_error,
                self.net_return_mean,
                self.net_return_standard_error,
            )
        ):
            raise ValueError("invalid final-test metrics")
        if self.contaminated and self.quality_passed:
            raise ValueError("contaminated final evidence cannot pass quality")
        _limitations(self.limitations, "artifact limitations")
        if self.artifact_hash != canonical_json_hash(self._content_dict()):
            raise ValueError("final-test artifact hash mismatch")

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "factor_spec_id": self.factor_spec_id,
            "candidate_hash": self.candidate_hash,
            "definition_hash": self.definition_hash,
            "transform_pipeline_hash": self.transform_pipeline_hash,
            "cost_model_hash": self.cost_model_hash,
            "regime_config_hash": self.regime_config_hash,
            "policy_hash": self.policy_hash,
            "data_snapshot_hash": self.data_snapshot_hash,
            "data_scope": self.data_scope,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "effective_observations": self.effective_observations,
            "rank_ic_mean": self.rank_ic_mean,
            "rank_ic_standard_error": self.rank_ic_standard_error,
            "net_return_mean": self.net_return_mean,
            "net_return_standard_error": self.net_return_standard_error,
            "quality_passed": self.quality_passed,
            "contaminated": self.contaminated,
            "access_audit": [item.to_dict() for item in self.access_audit],
            "limitations": list(self.limitations),
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._content_dict(), "artifact_hash": self.artifact_hash}


@dataclass(frozen=True)
class FinalDecisionEvidenceView:
    schema_version: Literal["final_decision_evidence_view.v1"]
    factor_spec_id: str
    final_test_artifact_hash: str
    frozen: bool
    one_shot: bool
    contaminated: bool
    quality_passed: bool
    final_oos_ic: float
    limitations: tuple[str, ...]
    view_hash: str

    def __post_init__(self) -> None:
        if self.schema_version != "final_decision_evidence_view.v1":
            raise ValueError("unsupported final decision view schema")
        _hash(self.final_test_artifact_hash, "final_test_artifact_hash")
        _hash(self.view_hash, "view_hash")
        if not math.isfinite(self.final_oos_ic):
            raise ValueError("final_oos_ic must be finite")
        if self.contaminated and self.quality_passed:
            raise ValueError("contaminated decision view cannot pass quality")
        _limitations(self.limitations, "decision view limitations")
        if self.view_hash != canonical_json_hash(self._content_dict()):
            raise ValueError("final decision view hash mismatch")

    @classmethod
    def create(
        cls,
        *,
        artifact: FinalTestArtifact,
        contaminated: bool,
        limitations: tuple[str, ...],
    ) -> "FinalDecisionEvidenceView":
        content = {
            "schema_version": "final_decision_evidence_view.v1",
            "factor_spec_id": artifact.factor_spec_id,
            "final_test_artifact_hash": artifact.artifact_hash,
            "frozen": True,
            "one_shot": len(
                [item for item in artifact.access_audit if item.outcome == "allowed"]
            )
            == 1,
            "contaminated": contaminated,
            "quality_passed": artifact.quality_passed and not contaminated,
            "final_oos_ic": artifact.rank_ic_mean,
            "limitations": list(limitations),
        }
        return cls(
            schema_version="final_decision_evidence_view.v1",
            factor_spec_id=artifact.factor_spec_id,
            final_test_artifact_hash=artifact.artifact_hash,
            frozen=True,
            one_shot=bool(content["one_shot"]),
            contaminated=contaminated,
            quality_passed=bool(content["quality_passed"]),
            final_oos_ic=artifact.rank_ic_mean,
            limitations=limitations,
            view_hash=canonical_json_hash(content),
        )

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "factor_spec_id": self.factor_spec_id,
            "final_test_artifact_hash": self.final_test_artifact_hash,
            "frozen": self.frozen,
            "one_shot": self.one_shot,
            "contaminated": self.contaminated,
            "quality_passed": self.quality_passed,
            "final_oos_ic": self.final_oos_ic,
            "limitations": list(self.limitations),
        }

    def to_decision_record(self) -> DecisionEvidenceRecord:
        return DecisionEvidenceRecord.create(
            evidence_kind="final_test",
            factor_spec_id=self.factor_spec_id,
            payload={
                "source_artifact_hash": self.final_test_artifact_hash,
                "view_hash": self.view_hash,
                "frozen": self.frozen,
                "one_shot": self.one_shot,
                "contaminated": self.contaminated,
                "quality_passed": self.quality_passed,
                "final_oos_ic": self.final_oos_ic,
                "limitations": list(self.limitations),
            },
        )


__all__ = [
    "FinalDecisionEvidenceView",
    "FinalTestAccessAudit",
    "FinalTestArtifact",
    "FinalTestDataRequest",
    "FinalTestDataset",
    "FinalTestPolicy",
    "FrozenFinalCandidate",
]
