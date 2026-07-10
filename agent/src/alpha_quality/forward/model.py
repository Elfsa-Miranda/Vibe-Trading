"""Immutable v2 forward plan, observation, and monitoring-only view."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from src.alpha_quality.decision_v2.model import DecisionEvidenceRecord
from src.research_ledger.hash_utils import canonical_json_hash

_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def _hash(value: str, name: str) -> None:
    if not isinstance(value, str) or _HASH_RE.fullmatch(value) is None:
        raise ValueError(f"{name} must be a canonical sha256 hash")


def _date(value: str, name: str) -> None:
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an ISO date") from exc


def _timestamp(value: str, name: str) -> None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{name} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{name} must include timezone")


@dataclass(frozen=True)
class FrozenForwardPlan:
    schema_version: Literal["frozen_forward_plan.v2"]
    plan_id: str
    factor_spec_id: str
    final_test_artifact_hash: str
    definition_hash: str
    transform_pipeline_hash: str
    cost_model_hash: str
    regime_config_hash: str
    policy_hash: str
    expected_horizon: int
    minimum_effective_observations: int
    minimum_rank_ic: float
    maximum_drawdown: float
    kill_rules_hash: str
    created_at: str
    plan_hash: str

    def __post_init__(self) -> None:
        if self.schema_version != "frozen_forward_plan.v2" or not self.plan_id:
            raise ValueError("unsupported forward plan schema or empty plan ID")
        for name in (
            "final_test_artifact_hash",
            "definition_hash",
            "transform_pipeline_hash",
            "cost_model_hash",
            "regime_config_hash",
            "policy_hash",
            "kill_rules_hash",
            "plan_hash",
        ):
            _hash(getattr(self, name), name)
        if self.expected_horizon < 1 or self.minimum_effective_observations < 1:
            raise ValueError("forward horizon and minimum observations must be positive")
        if not math.isfinite(self.minimum_rank_ic) or not math.isfinite(self.maximum_drawdown):
            raise ValueError("forward kill thresholds must be finite")
        if self.maximum_drawdown <= 0.0:
            raise ValueError("maximum_drawdown must be positive")
        _timestamp(self.created_at, "created_at")
        if self.plan_hash != canonical_json_hash(self._content_dict(include_plan_id=False)):
            raise ValueError("forward plan hash mismatch")
        expected_id = "forward-plan-" + self.plan_hash.removeprefix("sha256:")[:24]
        if self.plan_id != expected_id:
            raise ValueError("forward plan ID must derive from frozen content")

    @classmethod
    def create(
        cls,
        *,
        factor_spec_id: str,
        final_test_artifact_hash: str,
        definition_hash: str,
        transform_pipeline_hash: str,
        cost_model_hash: str,
        regime_config_hash: str,
        policy_hash: str,
        expected_horizon: int,
        minimum_effective_observations: int,
        minimum_rank_ic: float,
        maximum_drawdown: float,
        kill_rules_hash: str,
        created_at: str,
    ) -> "FrozenForwardPlan":
        content = {
            "schema_version": "frozen_forward_plan.v2",
            "factor_spec_id": factor_spec_id,
            "final_test_artifact_hash": final_test_artifact_hash,
            "definition_hash": definition_hash,
            "transform_pipeline_hash": transform_pipeline_hash,
            "cost_model_hash": cost_model_hash,
            "regime_config_hash": regime_config_hash,
            "policy_hash": policy_hash,
            "expected_horizon": expected_horizon,
            "minimum_effective_observations": minimum_effective_observations,
            "minimum_rank_ic": minimum_rank_ic,
            "maximum_drawdown": maximum_drawdown,
            "kill_rules_hash": kill_rules_hash,
            "created_at": created_at,
        }
        plan_hash = canonical_json_hash(content)
        return cls(
            schema_version="frozen_forward_plan.v2",
            plan_id="forward-plan-" + plan_hash.removeprefix("sha256:")[:24],
            factor_spec_id=factor_spec_id,
            final_test_artifact_hash=final_test_artifact_hash,
            definition_hash=definition_hash,
            transform_pipeline_hash=transform_pipeline_hash,
            cost_model_hash=cost_model_hash,
            regime_config_hash=regime_config_hash,
            policy_hash=policy_hash,
            expected_horizon=expected_horizon,
            minimum_effective_observations=minimum_effective_observations,
            minimum_rank_ic=minimum_rank_ic,
            maximum_drawdown=maximum_drawdown,
            kill_rules_hash=kill_rules_hash,
            created_at=created_at,
            plan_hash=plan_hash,
        )

    def _content_dict(self, *, include_plan_id: bool = True) -> dict[str, object]:
        content: dict[str, object] = {
            "schema_version": self.schema_version,
            "factor_spec_id": self.factor_spec_id,
            "final_test_artifact_hash": self.final_test_artifact_hash,
            "definition_hash": self.definition_hash,
            "transform_pipeline_hash": self.transform_pipeline_hash,
            "cost_model_hash": self.cost_model_hash,
            "regime_config_hash": self.regime_config_hash,
            "policy_hash": self.policy_hash,
            "expected_horizon": self.expected_horizon,
            "minimum_effective_observations": self.minimum_effective_observations,
            "minimum_rank_ic": self.minimum_rank_ic,
            "maximum_drawdown": self.maximum_drawdown,
            "kill_rules_hash": self.kill_rules_hash,
            "created_at": self.created_at,
        }
        if include_plan_id:
            content["plan_id"] = self.plan_id
        return content

    def to_dict(self) -> dict[str, object]:
        return {**self._content_dict(), "plan_hash": self.plan_hash}

    def to_decision_record(self) -> DecisionEvidenceRecord:
        return DecisionEvidenceRecord.create(
            evidence_kind="forward_plan",
            factor_spec_id=self.factor_spec_id,
            payload={
                "plan_hash": self.plan_hash,
                "frozen": True,
                "minimum_observations": self.minimum_effective_observations,
                "success_claim": False,
                "limitations": ["TRACKING_STARTED_NOT_SUCCESS"],
            },
        )


@dataclass(frozen=True)
class ForwardObservationV2:
    schema_version: Literal["forward_observation.v2"]
    observation_id: str
    plan_id: str
    plan_hash: str
    period_start: str
    period_end: str
    effective_observations: int
    rank_ic: float
    net_return: float
    drawdown: float
    previous_observation_hash: str | None
    observed_at: str
    observation_hash: str

    def __post_init__(self) -> None:
        if self.schema_version != "forward_observation.v2":
            raise ValueError("unsupported forward observation schema")
        _hash(self.plan_hash, "plan_hash")
        _hash(self.observation_hash, "observation_hash")
        if self.previous_observation_hash is not None:
            _hash(self.previous_observation_hash, "previous_observation_hash")
        _date(self.period_start, "period_start")
        _date(self.period_end, "period_end")
        _timestamp(self.observed_at, "observed_at")
        if self.period_end < self.period_start or self.effective_observations < 1:
            raise ValueError("invalid forward observation period or sample")
        if not all(math.isfinite(value) for value in (self.rank_ic, self.net_return, self.drawdown)):
            raise ValueError("forward metrics must be finite")
        if self.drawdown < 0.0:
            raise ValueError("drawdown must be non-negative")
        if self.observation_hash != canonical_json_hash(self._content_dict()):
            raise ValueError("forward observation hash mismatch")

    @classmethod
    def create(
        cls,
        *,
        plan: FrozenForwardPlan,
        period_start: str,
        period_end: str,
        effective_observations: int,
        rank_ic: float,
        net_return: float,
        drawdown: float,
        previous_observation_hash: str | None,
        observed_at: str,
    ) -> "ForwardObservationV2":
        observation_id = f"forward-observation-{plan.plan_id.removeprefix('forward-plan-')}-{period_end}"
        content = {
            "schema_version": "forward_observation.v2",
            "observation_id": observation_id,
            "plan_id": plan.plan_id,
            "plan_hash": plan.plan_hash,
            "period_start": period_start,
            "period_end": period_end,
            "effective_observations": effective_observations,
            "rank_ic": rank_ic,
            "net_return": net_return,
            "drawdown": drawdown,
            "previous_observation_hash": previous_observation_hash,
            "observed_at": observed_at,
        }
        return cls(
            schema_version="forward_observation.v2",
            observation_id=observation_id,
            plan_id=plan.plan_id,
            plan_hash=plan.plan_hash,
            period_start=period_start,
            period_end=period_end,
            effective_observations=effective_observations,
            rank_ic=rank_ic,
            net_return=net_return,
            drawdown=drawdown,
            previous_observation_hash=previous_observation_hash,
            observed_at=observed_at,
            observation_hash=canonical_json_hash(content),
        )

    def _content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "observation_id": self.observation_id,
            "plan_id": self.plan_id,
            "plan_hash": self.plan_hash,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "effective_observations": self.effective_observations,
            "rank_ic": self.rank_ic,
            "net_return": self.net_return,
            "drawdown": self.drawdown,
            "previous_observation_hash": self.previous_observation_hash,
            "observed_at": self.observed_at,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._content_dict(), "observation_hash": self.observation_hash}


@dataclass(frozen=True)
class MonitoringEvidenceView:
    schema_version: Literal["monitoring_evidence_view.v1"]
    scope: Literal["monitoring"]
    plan_id: str
    plan_hash: str
    factor_spec_id: str
    effective_observations: int
    status: Literal["insufficient", "monitoring", "kill_triggered"]
    observation_hashes: tuple[str, ...]
    success_statement: str | None
    limitations: tuple[str, ...]
    view_hash: str

    def __post_init__(self) -> None:
        if self.scope != "monitoring" or self.schema_version != "monitoring_evidence_view.v1":
            raise ValueError("invalid monitoring view scope or schema")
        _hash(self.plan_hash, "plan_hash")
        _hash(self.view_hash, "view_hash")
        if len(self.observation_hashes) != len(set(self.observation_hashes)):
            raise ValueError("monitoring observation hashes must be unique")


__all__ = ["ForwardObservationV2", "FrozenForwardPlan", "MonitoringEvidenceView"]
