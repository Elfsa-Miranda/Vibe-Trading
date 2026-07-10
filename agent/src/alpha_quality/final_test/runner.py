"""One-shot final evaluator; deterministic metrics, immutable artifact, no raw output."""

from __future__ import annotations

import math
import statistics
from pathlib import Path
from typing import Protocol

from src.alpha_quality.decision_v2.repository import DecisionEvidenceRepository
from src.alpha_quality.final_test.model import (
    FinalDecisionEvidenceView,
    FinalTestArtifact,
    FinalTestDataRequest,
    FinalTestDataset,
    FinalTestPolicy,
    FrozenFinalCandidate,
)
from src.alpha_quality.flags import ResolvedAGSFlags
from src.alpha_quality.scope.capabilities import TestScopeAuthority, TestScopeCapability
from src.research_ledger.events import EventDraft, ResearchEventStore
from src.research_ledger.hash_utils import canonical_json, canonical_json_hash


class FinalTestDataProvider(Protocol):
    def load_final(self, request: FinalTestDataRequest) -> FinalTestDataset: ...


class FinalTestRunner:
    def __init__(
        self,
        *,
        flags: ResolvedAGSFlags,
        authority: TestScopeAuthority,
        provider: FinalTestDataProvider,
        policy: FinalTestPolicy,
        store: ResearchEventStore,
    ) -> None:
        if not flags.enabled("VIBE_TRADING_DECISION_V2"):
            raise RuntimeError("final-test runner is disabled")
        self.authority = authority
        self.provider = provider
        self.policy = policy
        self.store = store

    def run(
        self,
        candidate: FrozenFinalCandidate,
        capability: TestScopeCapability,
        request: FinalTestDataRequest,
        *,
        run_id: str,
    ) -> FinalTestArtifact:
        if candidate.policy_hash != self.policy.policy_hash:
            raise ValueError("frozen candidate policy does not match final runner")
        audit = self.authority.authorize(capability, request)
        dataset = self.provider.load_final(request)
        if (
            dataset.data_snapshot_hash != request.data_snapshot_hash
            or dataset.period_start != request.period_start
            or dataset.period_end != request.period_end
        ):
            self.authority.contaminate_after_access(
                capability,
                request,
                reason_code="FINAL_PROVIDER_SCOPE_MISMATCH",
            )
            raise ValueError("final provider returned mismatched frozen data scope")
        count = len(dataset.rank_ic_series)
        rank_mean, rank_se = _mean_and_standard_error(dataset.rank_ic_series)
        net_mean, net_se = _mean_and_standard_error(dataset.net_returns)
        contaminated = self.authority.is_tainted(candidate.candidate_hash)
        quality_passed = (
            not contaminated
            and count >= self.policy.minimum_effective_observations
            and rank_mean >= self.policy.minimum_rank_ic_mean
            and net_mean >= self.policy.minimum_net_return_mean
        )
        limitations = set(dataset.limitations)
        limitations.add("FINAL_TEST_DECISION_ONLY")
        if count < self.policy.minimum_effective_observations:
            limitations.add("FINAL_TEST_SAMPLE_INSUFFICIENT")
        if contaminated:
            limitations.add("FINAL_SCOPE_CONTAMINATED")
        content: dict[str, object] = {
            "schema_version": "final_test_artifact.v1",
            "factor_spec_id": candidate.factor_spec_id,
            "candidate_hash": candidate.candidate_hash,
            "definition_hash": candidate.definition_hash,
            "transform_pipeline_hash": candidate.transform_pipeline_hash,
            "cost_model_hash": candidate.cost_model_hash,
            "regime_config_hash": candidate.regime_config_hash,
            "policy_hash": candidate.policy_hash,
            "data_snapshot_hash": candidate.data_snapshot_hash,
            "data_scope": "test",
            "period_start": request.period_start,
            "period_end": request.period_end,
            "effective_observations": count,
            "rank_ic_mean": rank_mean,
            "rank_ic_standard_error": rank_se,
            "net_return_mean": net_mean,
            "net_return_standard_error": net_se,
            "quality_passed": quality_passed,
            "contaminated": contaminated,
            "access_audit": [audit.to_dict()],
            "limitations": sorted(limitations),
        }
        artifact = FinalTestArtifact(
            schema_version="final_test_artifact.v1",
            factor_spec_id=candidate.factor_spec_id,
            candidate_hash=candidate.candidate_hash,
            definition_hash=candidate.definition_hash,
            transform_pipeline_hash=candidate.transform_pipeline_hash,
            cost_model_hash=candidate.cost_model_hash,
            regime_config_hash=candidate.regime_config_hash,
            policy_hash=candidate.policy_hash,
            data_snapshot_hash=candidate.data_snapshot_hash,
            data_scope="test",
            period_start=request.period_start,
            period_end=request.period_end,
            effective_observations=count,
            rank_ic_mean=rank_mean,
            rank_ic_standard_error=rank_se,
            net_return_mean=net_mean,
            net_return_standard_error=net_se,
            quality_passed=quality_passed,
            contaminated=contaminated,
            access_audit=(audit,),
            limitations=tuple(sorted(limitations)),
            artifact_hash=canonical_json_hash(content),
        )
        reference = self._persist_artifact(artifact)
        artifact_id = "final-artifact-" + artifact.artifact_hash.removeprefix("sha256:")[:24]
        self.store.append_event(
            EventDraft(
                event_type="FinalTestArtifactRecorded",
                entity_id=artifact_id,
                run_id=run_id,
                payload_schema_version="final_test_artifact_recorded.v1",
                idempotency_key="final-artifact:" + artifact.artifact_hash,
                payload={
                    "artifact_id": artifact_id,
                    "artifact_hash": artifact.artifact_hash,
                    "factor_spec_id": artifact.factor_spec_id,
                    "candidate_hash": artifact.candidate_hash,
                    "definition_hash": artifact.definition_hash,
                    "transform_pipeline_hash": artifact.transform_pipeline_hash,
                    "cost_model_hash": artifact.cost_model_hash,
                    "regime_config_hash": artifact.regime_config_hash,
                    "access_event_hash": audit.access_event_hash,
                    "policy_hash": artifact.policy_hash,
                    "data_snapshot_hash": artifact.data_snapshot_hash,
                    "effective_observations": artifact.effective_observations,
                    "quality_passed": artifact.quality_passed,
                    "contaminated": artifact.contaminated,
                    "artifact_refs": [reference],
                },
            )
        )
        return artifact

    def final_decision_view(
        self,
        artifact: FinalTestArtifact,
    ) -> FinalDecisionEvidenceView:
        contaminated = artifact.contaminated or self.authority.is_tainted(
            artifact.candidate_hash
        )
        limitations = set(artifact.limitations)
        if contaminated:
            limitations.add("FINAL_SCOPE_CONTAMINATED")
        return FinalDecisionEvidenceView.create(
            artifact=artifact,
            contaminated=contaminated,
            limitations=tuple(sorted(limitations)),
        )

    def record_decision_evidence(
        self,
        artifact: FinalTestArtifact,
        repository: DecisionEvidenceRepository,
    ) -> str:
        return repository.put(self.final_decision_view(artifact).to_decision_record())

    def _persist_artifact(self, artifact: FinalTestArtifact) -> dict[str, str]:
        relative = Path("final_test") / (
            artifact.artifact_hash.removeprefix("sha256:") + ".json"
        )
        path = self.store.artifact_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            temporary = path.with_suffix(".tmp")
            temporary.write_text(canonical_json(artifact.to_dict()), encoding="utf-8")
            temporary.replace(path)
        return {
            "relative_path": relative.as_posix(),
            "artifact_hash": self.store.hash_artifact(path),
            "media_type": "application/json",
        }


def _mean_and_standard_error(values: tuple[float, ...]) -> tuple[float, float]:
    mean = math.fsum(values) / len(values)
    standard_error = 0.0
    if len(values) > 1:
        standard_error = statistics.stdev(values) / math.sqrt(len(values))
    return mean, standard_error


__all__ = ["FinalTestDataProvider", "FinalTestRunner"]
