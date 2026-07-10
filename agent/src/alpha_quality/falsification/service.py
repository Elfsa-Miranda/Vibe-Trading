"""Feature-gated append-only registration, access, and fixed-result service."""

from __future__ import annotations

from pathlib import Path

from src.alpha_quality.falsification.contract import FalsificationContract
from src.alpha_quality.falsification.executor import FixedFamilyResult
from src.alpha_quality.flags import ResolvedAGSFlags
from src.research_ledger.events import EventDraft, ResearchEventStore
from src.research_ledger.hash_utils import canonical_json, canonical_json_hash, utc_now_iso


class FalsificationService:
    def __init__(self, *, store: ResearchEventStore, flags: ResolvedAGSFlags) -> None:
        if not flags.enabled("VIBE_TRADING_FALSIFICATION_CONTRACT"):
            raise RuntimeError("falsification contract capability is disabled")
        self.store = store

    def register(self, contract: FalsificationContract, *, run_id: str):
        prior_access = self.store.query_events(event_type="OutcomeDataAccessed")
        if any(event.payload["factor_spec_id"] == contract.factor_spec_id for event in prior_access):
            raise ValueError("outcome data was accessed before contract registration")
        now = utc_now_iso()
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

    def outcome_access(self, contract: FalsificationContract, *, data_scope: str = "valid") -> None:
        registered = self.store.query_events(
            event_type="FalsificationContractRegistered", entity_id=contract.contract_id
        )
        if registered:
            return
        access_id = "access-" + contract.factor_spec_id
        self.store.append_event(
            EventDraft(
                event_type="OutcomeDataAccessed",
                entity_id=access_id,
                run_id="falsification-access",
                payload_schema_version="outcome_data_accessed.v1",
                idempotency_key="outcome-access:" + contract.factor_spec_id,
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
        self.outcome_access(contract)
        artifact = {
            "schema_version": "fixed_falsification_artifact.v1",
            "contract_id": contract.contract_id,
            "contract_hash": contract.contract_hash,
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
