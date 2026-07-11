"""Append-only production persistence for immutable ComplementEvidence.v2."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from src.alpha_quality.complement.engine import (
    ComplementEngine,
    ComplementInputs,
)
from src.alpha_quality.complement.model import ComplementEvidenceV2, ComplementPolicy
from src.alpha_quality.flags import ResolvedAGSFlags
from src.research_ledger.events import EventDraft, ResearchEventEnvelope, ResearchEventStore
from src.research_ledger.hash_utils import canonical_json, canonical_json_hash


@dataclass(frozen=True)
class RecordedComplementEvidence:
    evidence: ComplementEvidenceV2
    event: ResearchEventEnvelope
    artifact_reference: Mapping[str, str]


class ComplementEvidenceService:
    """Compute outside the ledger transaction, then append one source-bound event."""

    def __init__(
        self,
        *,
        store: ResearchEventStore,
        flags: ResolvedAGSFlags,
        policy: ComplementPolicy,
    ) -> None:
        if not flags.enabled("VIBE_TRADING_COMPLEMENT_V2"):
            raise RuntimeError("ComplementEvidence.v2 capability is disabled")
        self.store = store
        self.policy = policy
        self._engine = ComplementEngine(flags=flags, policy=policy)

    def evaluate_and_record(
        self,
        inputs: ComplementInputs,
        *,
        source_evaluation_event_hash: str,
        source_terminal_event_hash: str,
        run_id: str,
    ) -> RecordedComplementEvidence:
        self._validate_sources(
            factor_spec_id=inputs.candidate_identity.factor_spec_id,
            data_scope=inputs.data_scope,
            evaluation_event_hash=source_evaluation_event_hash,
            terminal_event_hash=source_terminal_event_hash,
        )
        if inputs.data_scope != self.policy.data_scope:
            raise ValueError("complement inputs do not match the frozen policy scope")
        evidence = self._engine.evaluate(inputs)
        artifact = {
            "schema_version": "complement_evidence_artifact.v2",
            "evidence": evidence.to_dict(),
            "source_evaluation_event_hash": source_evaluation_event_hash,
            "source_terminal_event_hash": source_terminal_event_hash,
        }
        artifact_content_hash = canonical_json_hash(artifact)
        relative = Path("complement_v2") / (
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
        complement_id = "complement-" + evidence.complement_hash.removeprefix("sha256:")[:24]
        event = self.store.append_event(
            EventDraft(
                event_type="ComplementEvidenceRecorded",
                entity_id=complement_id,
                run_id=run_id,
                payload_schema_version="complement_evidence_recorded.v2",
                idempotency_key=(
                    f"complement:{evidence.complement_hash}:"
                    f"{source_evaluation_event_hash}:{source_terminal_event_hash}"
                ),
                payload={
                    "complement_id": complement_id,
                    "factor_spec_id": evidence.factor_spec_id,
                    "complement_hash": evidence.complement_hash,
                    "policy_version": evidence.policy_version,
                    "policy_hash": evidence.policy_hash,
                    "data_scope": evidence.data_scope,
                    "snapshot_hash": evidence.snapshot_hash,
                    "source_evaluation_event_hash": source_evaluation_event_hash,
                    "source_terminal_event_hash": source_terminal_event_hash,
                    "pool_factor_spec_ids": sorted(
                        identity.factor_spec_id for identity in inputs.existing_identities
                    ),
                    "identity_hash": evidence.identity.identity_hash,
                    "residual_hash": evidence.residual.evidence_hash,
                    "portfolio_hash": evidence.portfolio.evidence_hash,
                    "portfolio_construction_hash": self.policy.portfolio_construction_hash,
                    "cost_model_hash": self.policy.cost_model_hash,
                    "capacity_model_hash": self.policy.capacity_model_hash,
                    "exposure_model_hash": self.policy.exposure_model_hash,
                    "status": evidence.status,
                    "cap": evidence.cap,
                    "artifact_refs": [artifact_reference],
                },
            )
        )
        return RecordedComplementEvidence(
            evidence=evidence,
            event=event,
            artifact_reference=artifact_reference,
        )

    def _validate_sources(
        self,
        *,
        factor_spec_id: str,
        data_scope: str,
        evaluation_event_hash: str,
        terminal_event_hash: str,
    ) -> None:
        events = self.store.query_events()
        definitions = {
            str(event.payload["factor_spec_id"])
            for event in events
            if event.event_type == "FactorDefinitionRecorded"
        }
        evaluation = next(
            (
                event
                for event in events
                if event.event_type == "EvaluationRecorded"
                and event.event_hash == evaluation_event_hash
            ),
            None,
        )
        terminal = next(
            (
                event
                for event in events
                if event.event_type == "TrialTerminated"
                and event.event_hash == terminal_event_hash
            ),
            None,
        )
        if factor_spec_id not in definitions or evaluation is None or terminal is None:
            raise ValueError("complement evidence requires prior definition/evaluation/terminal")
        if (
            evaluation.payload["factor_spec_id"] != factor_spec_id
            or evaluation.payload["data_scope"] != data_scope
            or data_scope not in {"valid", "train_valid"}
            or terminal.payload["trial_id"] != evaluation.payload["trial_id"]
            or terminal.payload["status"] not in {"success", "reject"}
        ):
            raise ValueError("complement source evidence does not match frozen scope or trial")
        if terminal.payload["status"] == "success" and (
            terminal.payload["evaluation_event_hash"] != evaluation_event_hash
        ):
            raise ValueError("successful terminal does not reference complement evaluation")


__all__ = ["ComplementEvidenceService", "RecordedComplementEvidence"]
