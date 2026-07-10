"""Feature-gated append-only registration, access, and fixed-result service."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from src.alpha_quality.falsification.contract import FalsificationContract
from src.alpha_quality.falsification.executor import FixedFamilyResult
from src.alpha_quality.flags import ResolvedAGSFlags
from src.research_ledger.events import (
    EventDraft,
    EventIdempotencyConflict,
    ResearchEventStore,
)
from src.research_ledger.hash_utils import canonical_json, canonical_json_hash, utc_now_iso


class FalsificationService:
    def __init__(self, *, store: ResearchEventStore, flags: ResolvedAGSFlags) -> None:
        if not flags.enabled("VIBE_TRADING_FALSIFICATION_CONTRACT"):
            raise RuntimeError("falsification contract capability is disabled")
        self.store = store

    def register(self, contract: FalsificationContract, *, run_id: str):
        existing = self.store.query_events(
            event_type="FalsificationContractRegistered", entity_id=contract.contract_id
        )
        if existing:
            event = existing[-1]
            if event.payload["contract_hash"] != contract.contract_hash:
                raise ValueError("contract identity conflicts with an existing registration")
            return event
        prior_access = self.store.query_events(event_type="OutcomeDataAccessed")
        if any(event.payload["factor_spec_id"] == contract.factor_spec_id for event in prior_access):
            raise ValueError("outcome data was accessed before contract registration")
        now = utc_now_iso()
        try:
            return self.store.append_event(
                EventDraft(
                    event_type="FalsificationContractRegistered",
                    entity_id=contract.contract_id,
                    run_id=run_id,
                    payload_schema_version="falsification_contract_registered.v1",
                    idempotency_key="contract:" + contract.contract_hash,
                    payload={
                        "contract_id": contract.contract_id,
                        "contract_hash": contract.contract_hash,
                        "factor_spec_id": contract.factor_spec_id,
                        "registered_at": now,
                        "data_access_cutoff": now,
                        "policy_hash": contract.policy_hash,
                    },
                )
            )
        except EventIdempotencyConflict:
            concurrent = self.store.query_events(
                event_type="FalsificationContractRegistered",
                entity_id=contract.contract_id,
            )
            if (
                concurrent
                and concurrent[-1].run_id == run_id
                and concurrent[-1].payload["contract_hash"] == contract.contract_hash
            ):
                return concurrent[-1]
            raise

    def outcome_access(
        self,
        contract: FalsificationContract,
        *,
        data_scope: Literal["valid"] = "valid",
    ):
        if data_scope != "valid":
            raise ValueError("falsification outcome access is validation-only")
        registered = self.store.query_events(
            event_type="FalsificationContractRegistered", entity_id=contract.contract_id
        )
        if registered:
            if registered[-1].payload["contract_hash"] != contract.contract_hash:
                raise ValueError("registered contract hash does not match outcome request")
            access_id = "access-" + contract.contract_hash.removeprefix("sha256:")[:16]
            prior = self.store.query_events(event_type="OutcomeDataAccessed", entity_id=access_id)
            if prior:
                return prior[-1]
            try:
                return self.store.append_event(
                    EventDraft(
                        event_type="OutcomeDataAccessed",
                        entity_id=access_id,
                        run_id="falsification-access",
                        payload_schema_version="outcome_data_accessed.v1",
                        idempotency_key="outcome-access:" + contract.contract_hash,
                        payload={
                            "access_id": access_id,
                            "factor_spec_id": contract.factor_spec_id,
                            "data_scope": data_scope,
                            "accessed_at": utc_now_iso(),
                        },
                    )
                )
            except EventIdempotencyConflict:
                concurrent = self.store.query_events(
                    event_type="OutcomeDataAccessed", entity_id=access_id
                )
                if concurrent and concurrent[-1].payload["data_scope"] == data_scope:
                    return concurrent[-1]
                raise
        access_id = "access-unregistered-" + contract.factor_spec_id
        self.store.append_event(
            EventDraft(
                event_type="OutcomeDataAccessed",
                entity_id=access_id,
                run_id="falsification-access",
                payload_schema_version="outcome_data_accessed.v1",
                idempotency_key="outcome-access-unregistered:" + contract.factor_spec_id,
                payload={
                    "access_id": access_id,
                    "factor_spec_id": contract.factor_spec_id,
                    "data_scope": data_scope,
                    "accessed_at": utc_now_iso(),
                },
            )
        )
        raise ValueError("outcome access requires registered contract")

    def record_fixed_result(
        self,
        contract: FalsificationContract,
        result: FixedFamilyResult,
        *,
        run_id: str,
    ):
        contract.require_fixed_horizon()
        self.outcome_access(contract)
        artifact = {
            "schema_version": "fixed_falsification_artifact.v2",
            "contract_id": contract.contract_id,
            "contract_hash": contract.contract_hash,
            "contract_snapshot": dict(contract.__dict__),
            "factor_spec_id": contract.factor_spec_id,
            "data_scope": "valid",
            "decisive": contract.decisive,
            "policy_hash": contract.policy_hash,
            "result": result.to_dict(),
        }
        artifact_hash = canonical_json_hash(artifact)
        relative = Path("falsification") / (artifact_hash.removeprefix("sha256:") + ".json")
        path = self.store.artifact_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            temporary = path.with_suffix(".tmp")
            temporary.write_text(canonical_json(artifact), encoding="utf-8")
            temporary.replace(path)
        result_id = "result-" + artifact_hash.removeprefix("sha256:")[:16]
        return self.store.append_event(
            EventDraft(
                event_type="FalsificationResultRecorded",
                entity_id=result_id,
                run_id=run_id,
                payload_schema_version="falsification_result_recorded.v1",
                idempotency_key="falsification-result:" + artifact_hash,
                payload={
                    "result_id": result_id,
                    "contract_id": contract.contract_id,
                    "contract_hash": contract.contract_hash,
                    "outcome": result.outcome,
                    "artifact_refs": [
                        {
                            "relative_path": relative.as_posix(),
                            "artifact_hash": self.store.hash_artifact(path),
                            "media_type": "application/json",
                        }
                    ],
                },
            )
        )


__all__ = ["FalsificationService"]
