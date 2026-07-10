"""Append-only production wiring for deterministic Decision v2."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from src.alpha_quality.decision_v2.model import (
    AlphaQualityDecisionV2,
    DecisionEvidenceRefs,
)
from src.alpha_quality.decision_v2.policy import DecisionV2Policy
from src.alpha_quality.decision_v2.repository import DecisionEvidenceRepository
from src.alpha_quality.decision_v2.runner import QualityDecisionV2Runner
from src.alpha_quality.flags import ResolvedAGSFlags
from src.research_ledger.events import EventDraft, ResearchEventEnvelope, ResearchEventStore
from src.research_ledger.hash_utils import canonical_json, canonical_json_hash


@dataclass(frozen=True)
class RecordedQualityDecisionV2:
    decision: AlphaQualityDecisionV2
    event: ResearchEventEnvelope
    artifact_reference: Mapping[str, str]


class QualityDecisionV2Service:
    def __init__(
        self,
        *,
        store: ResearchEventStore,
        flags: ResolvedAGSFlags,
        policy: DecisionV2Policy,
        repository: DecisionEvidenceRepository,
    ) -> None:
        if not flags.enabled("VIBE_TRADING_DECISION_V2"):
            raise RuntimeError("Decision v2 capability is disabled")
        self.store = store
        self.policy = policy
        self.runner = QualityDecisionV2Runner(
            flags=flags,
            policy=policy,
            repository=repository,
        )

    def decide_and_record(
        self,
        refs: DecisionEvidenceRefs,
        *,
        run_id: str,
    ) -> RecordedQualityDecisionV2:
        decision = self.runner.run(refs)
        artifact = {
            "schema_version": "quality_decision_artifact.v2",
            "evidence_refs": refs.to_dict(),
            "decision": decision.to_dict(),
        }
        artifact_content_hash = canonical_json_hash(artifact)
        relative = Path("decision_v2") / (
            artifact_content_hash.removeprefix("sha256:") + ".json"
        )
        path = self.store.artifact_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            temporary = path.with_suffix(".tmp")
            temporary.write_text(canonical_json(artifact), encoding="utf-8")
            temporary.replace(path)
        artifact_reference = {
            "relative_path": relative.as_posix(),
            "artifact_hash": self.store.hash_artifact(path),
            "media_type": "application/json",
        }
        decision_id = "decision-v2-" + decision.decision_hash.removeprefix("sha256:")[:24]
        ref_payload = refs.to_dict()
        ref_payload.pop("factor_spec_id")
        event = self.store.append_event(
            EventDraft(
                event_type="QualityDecisionV2Recorded",
                entity_id=decision_id,
                run_id=run_id,
                payload_schema_version="quality_decision_recorded.v2",
                idempotency_key="quality-decision-v2:" + decision.decision_hash,
                payload={
                    "decision_id": decision_id,
                    "factor_spec_id": decision.factor_spec_id,
                    "decision_hash": decision.decision_hash,
                    "decision": decision.decision,
                    "tier": decision.tier,
                    "policy_version": decision.policy_version,
                    "policy_hash": decision.policy_hash,
                    **ref_payload,
                    "evidence_hashes": list(decision.evidence_hashes),
                    "reasons": list(decision.reasons),
                    "warnings": list(decision.warnings),
                    "caps": list(decision.caps),
                    "limitations": list(decision.limitations),
                    "within_tier_score": decision.within_tier_score,
                    "forward_success_claim": decision.forward_success_claim,
                    "artifact_refs": [artifact_reference],
                },
            )
        )
        return RecordedQualityDecisionV2(
            decision=decision,
            event=event,
            artifact_reference=artifact_reference,
        )


__all__ = ["QualityDecisionV2Service", "RecordedQualityDecisionV2"]
