"""Registered fixed-budget paired execution boundary for activation experiments."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal, cast

from src.alpha_foundry.activation.artifacts import ActivationArtifactStore
from src.alpha_foundry.activation.model import (
    ActivationExperimentPlan,
    ActivationRunManifest,
)


_REGISTRATION_AUTHORITY = object()
_SCOPE_AUTHORITY = object()


@dataclass(frozen=True, init=False)
class RegisteredActivationPlan:
    plan: ActivationExperimentPlan
    relative_artifact: str
    _authority: object

    def __init__(
        self,
        plan: ActivationExperimentPlan,
        relative_artifact: str,
        *,
        _authority: object,
    ) -> None:
        if _authority is not _REGISTRATION_AUTHORITY:
            raise TypeError("activation plans must be registered by the paired runner")
        object.__setattr__(self, "plan", plan)
        object.__setattr__(self, "relative_artifact", relative_artifact)
        object.__setattr__(self, "_authority", _authority)


@dataclass(frozen=True, init=False)
class TrainValidActivationScope:
    train_snapshot_hash: str
    valid_snapshot_hash: str
    discovery_chain_head: str
    _authority: object

    def __init__(
        self,
        *,
        train_snapshot_hash: str,
        valid_snapshot_hash: str,
        discovery_chain_head: str,
        _authority: object,
    ) -> None:
        if _authority is not _SCOPE_AUTHORITY:
            raise TypeError("activation scope is issued only from a registered plan")
        object.__setattr__(self, "train_snapshot_hash", train_snapshot_hash)
        object.__setattr__(self, "valid_snapshot_hash", valid_snapshot_hash)
        object.__setattr__(self, "discovery_chain_head", discovery_chain_head)
        object.__setattr__(self, "_authority", _authority)


@dataclass(frozen=True)
class ActivationArmRequest:
    plan_hash: str
    pair_id: str
    run_group_id: str
    arm: Literal["control", "treatment"]
    seed: int
    mechanism_family: str
    dag_region: str
    policy_hash: str
    rng_namespace: str
    cache_namespace: str
    candidate_budget: int
    compute_budget: int


ArmExecutor = Callable[[ActivationArmRequest, TrainValidActivationScope], ActivationRunManifest]


class PairedActivationRunner:
    def __init__(self, artifact_store: ActivationArtifactStore) -> None:
        self.artifact_store = artifact_store

    def register(self, plan: ActivationExperimentPlan) -> RegisteredActivationPlan:
        relative = self.artifact_store.put("plan", plan.to_dict())
        return RegisteredActivationPlan(plan, relative, _authority=_REGISTRATION_AUTHORITY)

    def run_pair(
        self,
        registered: RegisteredActivationPlan,
        *,
        run_group_id: str,
        mechanism_family: str,
        dag_region: str,
        executor: ArmExecutor,
    ) -> tuple[ActivationRunManifest, ActivationRunManifest]:
        if not isinstance(registered, RegisteredActivationPlan) or registered._authority is not _REGISTRATION_AUTHORITY:
            raise TypeError("formal outcomes require a registered immutable plan")
        plan = registered.plan
        if plan.phase != "confirmatory":
            raise ValueError("pilot plans cannot produce a confirmatory pair")
        if run_group_id not in plan.design.run_group_ids:
            raise ValueError("run group is outside the fixed stopping set")
        if run_group_id in plan.design.pilot_excluded_run_group_ids:
            raise ValueError("pilot run group is permanently excluded")
        if mechanism_family not in plan.design.mechanism_families or dag_region not in plan.design.dag_regions:
            raise ValueError("pair stratum is not preregistered")
        index = plan.design.run_group_ids.index(run_group_id)
        seed = plan.design.seeds[index]
        pair_id = f"{run_group_id}:{mechanism_family}:{dag_region}"
        scope = TrainValidActivationScope(
            train_snapshot_hash=plan.provenance.train_snapshot_hash,
            valid_snapshot_hash=plan.provenance.valid_snapshot_hash,
            discovery_chain_head=plan.provenance.eligible_event_chain_head,
            _authority=_SCOPE_AUTHORITY,
        )
        manifests: list[ActivationRunManifest] = []
        for arm, policy_hash in (
            ("control", plan.provenance.control_policy_hash),
            ("treatment", plan.provenance.treatment_policy_hash),
        ):
            request = ActivationArmRequest(
                plan_hash=plan.plan_hash,
                pair_id=pair_id,
                run_group_id=run_group_id,
                arm=cast(Literal["control", "treatment"], arm),
                seed=seed,
                mechanism_family=mechanism_family,
                dag_region=dag_region,
                policy_hash=policy_hash,
                rng_namespace=f"{plan.plan_hash}:{run_group_id}:{arm}:rng",
                cache_namespace=f"{plan.plan_hash}:{run_group_id}:{arm}:cache",
                candidate_budget=plan.design.candidate_budget,
                compute_budget=plan.design.compute_budget,
            )
            manifest = executor(request, scope)
            self._validate_response(request, manifest)
            self.artifact_store.put("run", manifest.to_dict())
            manifests.append(manifest)
        return manifests[0], manifests[1]

    @staticmethod
    def _validate_response(
        request: ActivationArmRequest,
        manifest: ActivationRunManifest,
    ) -> None:
        for name in (
            "plan_hash", "pair_id", "run_group_id", "arm", "seed", "mechanism_family",
            "dag_region", "policy_hash", "rng_namespace", "cache_namespace",
            "candidate_budget", "compute_budget",
        ):
            if getattr(manifest, name) != getattr(request, name):
                raise ValueError(f"executor changed frozen activation field: {name}")


__all__ = [
    "ActivationArmRequest", "ArmExecutor", "PairedActivationRunner",
    "RegisteredActivationPlan", "TrainValidActivationScope",
]
