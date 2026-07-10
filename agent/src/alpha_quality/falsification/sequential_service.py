"""Append-only production wiring for sequential falsification and ordinal MEI."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Sequence

from src.alpha_quality.falsification.contract import FalsificationContract
from src.alpha_quality.falsification.mei import (
    MechanismEvidenceIndex,
    MechanismEvidenceRef,
    aggregate_mechanism_evidence,
)
from src.alpha_quality.falsification.sequential import (
    APPROVED_METHOD,
    APPROVED_STOPPING_RULE,
    SequentialBlock,
    SequentialExecutor,
    SequentialLook,
    SequentialProtocol,
    SequentialState,
)
from src.alpha_quality.falsification.service import FalsificationService
from src.alpha_quality.flags import ResolvedAGSFlags
from src.research_ledger.events import (
    EventDraft,
    EventIdempotencyConflict,
    ResearchEventEnvelope,
    ResearchEventStore,
)
from src.research_ledger.events.artifacts import validate_artifact_references
from src.research_ledger.hash_utils import canonical_json, canonical_json_hash, utc_now_iso


class SequentialFalsificationService:
    """Narrow validation-only writer for pre-registered sequential evidence."""

    def __init__(self, *, store: ResearchEventStore, flags: ResolvedAGSFlags) -> None:
        if not flags.enabled("VIBE_TRADING_FALSIFICATION_CONTRACT"):
            raise RuntimeError("sequential falsification capability is disabled")
        self.store = store
        self._contracts = FalsificationService(store=store, flags=flags)
        self._executor = SequentialExecutor(flags=flags)

    @staticmethod
    def protocol_id(protocol: SequentialProtocol) -> str:
        return protocol.protocol_id

    @staticmethod
    def _validate_pair(
        contract: FalsificationContract, protocol: SequentialProtocol
    ) -> None:
        if not isinstance(contract, FalsificationContract) or not isinstance(
            protocol, SequentialProtocol
        ):
            raise TypeError("typed fixed contract and sequential protocol are required")
        if contract.is_fixed_horizon:
            raise ValueError("a fixed-horizon contract cannot register a sequential protocol")
        if protocol.maximum_looks < 2:
            raise ValueError("a sequential protocol requires at least two frozen looks")
        comparisons = {
            "factor_spec_id": contract.factor_spec_id == protocol.factor_spec_id,
            "maximum_looks": contract.maximum_looks == protocol.maximum_looks,
            "stopping_rule": contract.stopping_rule == protocol.stopping_rule,
            "direction": contract.direction == protocol.expected_direction,
            "policy_hash": contract.policy_hash == protocol.policy_hash,
            "sesoi": math.isclose(contract.sesoi, protocol.sesoi, rel_tol=0.0, abs_tol=1e-15),
            "family_alpha": math.isclose(
                contract.alpha, protocol.family_alpha, rel_tol=0.0, abs_tol=1e-15
            ),
        }
        mismatches = sorted(name for name, matches in comparisons.items() if not matches)
        if mismatches:
            raise ValueError(f"contract/protocol frozen fields mismatch: {mismatches}")
        if protocol.method != APPROVED_METHOD or protocol.stopping_rule != APPROVED_STOPPING_RULE:
            raise ValueError("sequential protocol method or stopping rule is not approved")

    def register_protocol(
        self,
        contract: FalsificationContract,
        protocol: SequentialProtocol,
        *,
        run_id: str,
    ) -> ResearchEventEnvelope:
        self._validate_pair(contract, protocol)
        self._contracts.register(contract, run_id=run_id)
        protocol_id = self.protocol_id(protocol)
        existing = self.store.query_events(
            event_type="SequentialProtocolRegistered", entity_id=protocol_id
        )
        if existing:
            event = existing[-1]
            if (
                event.payload["protocol_hash"] != protocol.protocol_hash
                or event.payload["contract_hash"] != contract.contract_hash
            ):
                raise ValueError("sequential protocol identity conflicts with prior registration")
            return event
        payload = {
            "protocol_id": protocol_id,
            "protocol_hash": protocol.protocol_hash,
            "contract_id": contract.contract_id,
            "contract_hash": contract.contract_hash,
            "factor_spec_id": protocol.factor_spec_id,
            "method": protocol.method,
            "maximum_looks": protocol.maximum_looks,
            "stopping_rule": protocol.stopping_rule,
            "data_scope": protocol.scope,
            "family_alpha": protocol.family_alpha,
            "support_alpha": protocol.support_alpha,
            "contradiction_alpha": protocol.contradiction_alpha,
            "lambda_grid": list(protocol.lambda_grid),
            "mixture_weights": list(protocol.mixture_weights),
            "support_log_boundary": protocol.support_log_boundary,
            "contradiction_log_boundary": protocol.contradiction_log_boundary,
            "filtration_hash": protocol.filtration_hash,
            "block_schedule_hash": protocol.block_schedule_hash,
            "policy_hash": protocol.policy_hash,
            "registered_at": utc_now_iso(),
        }
        try:
            return self.store.append_event(
                EventDraft(
                    event_type="SequentialProtocolRegistered",
                    entity_id=protocol_id,
                    run_id=run_id,
                    payload_schema_version="sequential_protocol_registered.v1",
                    payload=payload,
                    idempotency_key="sequential-protocol:" + protocol.protocol_hash,
                )
            )
        except EventIdempotencyConflict:
            concurrent = self.store.query_events(
                event_type="SequentialProtocolRegistered", entity_id=protocol_id
            )
            if (
                concurrent
                and concurrent[-1].run_id == run_id
                and concurrent[-1].payload["protocol_hash"] == protocol.protocol_hash
                and concurrent[-1].payload["contract_hash"] == contract.contract_hash
            ):
                return concurrent[-1]
            raise

    def record_look(
        self,
        contract: FalsificationContract,
        protocol: SequentialProtocol,
        block: SequentialBlock,
        look: SequentialLook,
        *,
        run_id: str,
    ) -> ResearchEventEnvelope:
        self._validate_pair(contract, protocol)
        protocol_id = self.protocol_id(protocol)
        registrations = self.store.query_events(
            event_type="SequentialProtocolRegistered", entity_id=protocol_id
        )
        if not registrations:
            raise ValueError("sequential protocol must be registered before a look")
        authoritative_state = self._authoritative_state(protocol)
        _, expected_look = self._executor.advance(protocol, authoritative_state, block)
        if look.look_hash != expected_look.look_hash:
            raise ValueError("caller look differs from deterministic sequential evidence")
        if block.information_time < len(block.observations):
            raise ValueError("information_time cannot precede the observed information count")
        expected = {
            "protocol_hash": look.protocol_hash == protocol.protocol_hash,
            "look_index": look.look_index >= 1,
            "information_time": look.information_time == block.information_time,
            "block_id": look.block_id == block.block_id,
            "block_hash": look.block_hash == block.block_hash,
            "unit_set_hash": look.unit_set_hash == block.unit_set_hash,
            "observation_count": look.observation_count == len(block.observations),
            "support_boundary": math.isclose(
                look.support_boundary, protocol.support_boundary, rel_tol=0.0, abs_tol=1e-12
            ),
            "contradiction_boundary": math.isclose(
                look.contradiction_boundary,
                protocol.contradiction_boundary,
                rel_tol=0.0,
                abs_tol=1e-12,
            ),
        }
        mismatches = sorted(name for name, matches in expected.items() if not matches)
        if mismatches:
            raise ValueError(f"look does not match deterministic block/protocol: {mismatches}")
        prior = [
            event
            for event in self.store.query_events(event_type="SequentialLookRecorded")
            if event.payload["protocol_id"] == protocol_id
        ]
        previous_event_hash = None if not prior else prior[-1].event_hash
        previous_information = 0 if not prior else int(prior[-1].payload["information_time"])
        incremental_information = len(block.observations)
        if block.information_time != previous_information + incremental_information:
            raise ValueError(
                "production sequential information_time must equal cumulative unique observations"
            )
        self._contracts.outcome_access(contract, data_scope="valid")
        look_id = f"look-{protocol.protocol_hash.removeprefix('sha256:')[:16]}-{look.look_index}"
        return self.store.append_event(
            EventDraft(
                event_type="SequentialLookRecorded",
                entity_id=look_id,
                run_id=run_id,
                payload_schema_version="sequential_look_recorded.v1",
                idempotency_key=f"sequential-look:{protocol.protocol_hash}:{look.look_index}",
                payload={
                    "look_id": look_id,
                    "protocol_id": protocol_id,
                    "protocol_hash": protocol.protocol_hash,
                    "factor_spec_id": protocol.factor_spec_id,
                    "look_index": look.look_index,
                    "information_time": look.information_time,
                    "block_id": look.block_id,
                    "block_hash": look.block_hash,
                    "unit_hashes": list(block.unit_hashes),
                    "incremental_information": incremental_information,
                    "support_component_log_capitals": list(
                        look.support_component_log_capitals
                    ),
                    "contradiction_component_log_capitals": list(
                        look.contradiction_component_log_capitals
                    ),
                    "cumulative_support_log_e": look.support_log_evidence,
                    "cumulative_contradiction_log_e": look.contradiction_log_evidence,
                    "support_log_boundary": protocol.support_log_boundary,
                    "contradiction_log_boundary": protocol.contradiction_log_boundary,
                    "status": look.status,
                    "stop_reason": look.stop_reason,
                    "previous_look_event_hash": previous_event_hash,
                },
            )
        )

    def record_block(
        self,
        contract: FalsificationContract,
        protocol: SequentialProtocol,
        block: SequentialBlock,
        *,
        run_id: str,
    ) -> ResearchEventEnvelope:
        """Judge one raw bounded block and persist only the deterministic look."""

        state = self._authoritative_state(protocol)
        _, look = self._executor.advance(protocol, state, block)
        return self.record_look(contract, protocol, block, look, run_id=run_id)

    def record_terminal_result(
        self,
        contract: FalsificationContract,
        protocol: SequentialProtocol,
        *,
        run_id: str,
    ) -> ResearchEventEnvelope:
        self._validate_pair(contract, protocol)
        protocol_id = self.protocol_id(protocol)
        looks = [
            event
            for event in self.store.query_events(event_type="SequentialLookRecorded")
            if event.payload["protocol_id"] == protocol_id
        ]
        if not looks or looks[-1].payload["status"] == "continue":
            raise ValueError("sequential result requires a terminal persisted look")
        terminal = looks[-1]
        outcome_by_status = {
            "support_boundary_crossed": "supported",
            "contradiction_boundary_crossed": "falsified",
            "max_looks_reached": "inconclusive",
        }
        outcome = outcome_by_status[str(terminal.payload["status"])]
        artifact = {
            "schema_version": "sequential_falsification_artifact.v1",
            "contract_id": contract.contract_id,
            "contract_hash": contract.contract_hash,
            "contract_snapshot": dict(contract.__dict__),
            "protocol_id": protocol_id,
            "protocol": protocol.to_dict(),
            "factor_spec_id": protocol.factor_spec_id,
            "data_scope": "valid",
            "decisive": protocol.decisive,
            "policy_hash": protocol.policy_hash,
            "terminal_look_event_hash": terminal.event_hash,
            "outcome": outcome,
            "reason_codes": [str(terminal.payload["stop_reason"])],
            "warning_codes": (
                ["SEQUENTIAL_EVIDENCE_INCONCLUSIVE"] if outcome == "inconclusive" else []
            ),
            "limitation_codes": ["VALIDATION_SCOPE_ONLY"],
        }
        artifact_hash, relative = self._write_artifact("sequential", artifact)
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
                    "outcome": outcome,
                    "artifact_refs": [
                        {
                            "relative_path": relative.as_posix(),
                            "artifact_hash": artifact_hash,
                            "media_type": "application/json",
                        }
                    ],
                },
            )
        )

    def evidence_ref(
        self,
        contract: FalsificationContract,
        result_event: ResearchEventEnvelope,
        *,
        policy_version: str,
    ) -> MechanismEvidenceRef:
        """Build an evidence role from a verified content-addressed artifact."""

        if result_event.event_type != "FalsificationResultRecorded":
            raise TypeError("MEI source must be a falsification result event")
        payload = result_event.payload
        if (
            payload["contract_id"] != contract.contract_id
            or payload["contract_hash"] != contract.contract_hash
        ):
            raise ValueError("MEI source contract does not match result event")
        references = payload["artifact_refs"]
        if len(references) != 1:
            raise ValueError("MEI source requires exactly one result artifact")
        reference = validate_artifact_references(
            self.store.artifact_root,
            [dict(references[0])],
        )[0]
        path = self.store.artifact_root / str(reference["relative_path"])
        if self.store.hash_artifact(path) != reference["artifact_hash"]:
            raise ValueError("MEI source artifact hash mismatch")
        artifact = json.loads(path.read_text(encoding="utf-8"))
        if artifact.get("schema_version") not in {
            "fixed_falsification_artifact.v2",
            "sequential_falsification_artifact.v1",
        }:
            raise ValueError("legacy result lacks v2 validation-scope/role provenance")
        if artifact.get("data_scope") != "valid":
            raise ValueError("MEI source must be validation-only evidence")
        snapshot = artifact.get("contract_snapshot")
        if not isinstance(snapshot, dict) or canonical_json_hash(snapshot) != contract.contract_hash:
            raise ValueError("MEI source contract snapshot is missing or mismatched")
        if (
            artifact.get("factor_spec_id") != contract.factor_spec_id
            or artifact.get("policy_hash") != contract.policy_hash
            or artifact.get("decisive") != contract.decisive
        ):
            raise ValueError("MEI source provenance does not match the frozen contract")
        raw_outcome = str(payload["outcome"])
        reason_codes: tuple[str, ...] = ()
        warning_codes: tuple[str, ...] = ()
        limitation_codes: tuple[str, ...] = ()
        if artifact["schema_version"] == "fixed_falsification_artifact.v2":
            result = artifact["result"]
            reason_codes = tuple(str(item) for item in result.get("failure_codes", []))
            warning_codes = tuple(str(item) for item in result.get("warnings", []))
            if raw_outcome == "inconclusive" and "LOW_POWER" in warning_codes:
                raw_outcome = "low_power"
            elif raw_outcome == "inconclusive" and any(
                code.endswith("UNAVAILABLE") or code.endswith("MISSING")
                for code in warning_codes
            ):
                raw_outcome = "unavailable"
        else:
            reason_codes = tuple(str(item) for item in artifact.get("reason_codes", []))
            warning_codes = tuple(str(item) for item in artifact.get("warning_codes", []))
            limitation_codes = tuple(
                str(item) for item in artifact.get("limitation_codes", [])
            )
        return MechanismEvidenceRef(
            factor_spec_id=contract.factor_spec_id,
            result_hash=str(reference["artifact_hash"]),
            event_hash=result_event.event_hash,
            policy_version=policy_version,
            policy_hash=contract.policy_hash,
            outcome=raw_outcome,  # type: ignore[arg-type]
            decisive=bool(artifact["decisive"]),
            reason_codes=reason_codes,
            warning_codes=warning_codes,
            limitation_codes=limitation_codes,
        )

    def aggregate_results(
        self,
        sources: Sequence[tuple[FalsificationContract, ResearchEventEnvelope]],
        *,
        factor_spec_id: str,
        policy_version: str,
        policy_hash: str,
    ) -> MechanismEvidenceIndex:
        references = tuple(
            self.evidence_ref(contract, event, policy_version=policy_version)
            for contract, event in sources
        )
        return aggregate_mechanism_evidence(
            references,
            factor_spec_id=factor_spec_id,
            policy_version=policy_version,
            policy_hash=policy_hash,
        )

    def record_mechanism_index(
        self, index: MechanismEvidenceIndex, *, run_id: str
    ) -> ResearchEventEnvelope:
        mei_id = "mei-" + index.mei_hash.removeprefix("sha256:")[:16]
        return self.store.append_event(
            EventDraft(
                event_type="MechanismEvidenceIndexRecorded",
                entity_id=mei_id,
                run_id=run_id,
                payload_schema_version="mechanism_evidence_index_recorded.v1",
                idempotency_key="mechanism-evidence-index:" + index.mei_hash,
                payload={
                    "mei_id": mei_id,
                    "factor_spec_id": index.factor_spec_id,
                    "mei_hash": index.mei_hash,
                    "mei_schema_version": index.schema_version,
                    "truth_table_version": index.truth_table_version,
                    "policy_version": index.policy_version,
                    "policy_hash": index.policy_hash,
                    "source_result_hashes": list(index.source_result_hashes),
                    "source_event_hashes": list(index.source_event_hashes),
                    "decisive_event_hashes": list(index.decisive_event_hashes),
                    "advisory_event_hashes": list(index.advisory_event_hashes),
                    "ordinal_state": index.ordinal_state,
                    "reason_codes": list(index.reason_codes),
                    "warning_codes": list(index.warning_codes),
                    "limitation_codes": list(index.limitation_codes),
                },
            )
        )

    def _write_artifact(
        self, namespace: str, payload: dict[str, object]
    ) -> tuple[str, Path]:
        artifact_hash = canonical_json_hash(payload)
        relative = Path("falsification") / namespace / (
            artifact_hash.removeprefix("sha256:") + ".json"
        )
        path = self.store.artifact_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            temporary = path.with_suffix(".tmp")
            temporary.write_text(canonical_json(payload), encoding="utf-8")
            temporary.replace(path)
        return artifact_hash, relative

    def _authoritative_state(self, protocol: SequentialProtocol) -> SequentialState:
        protocol_id = self.protocol_id(protocol)
        events = [
            event
            for event in self.store.query_events(event_type="SequentialLookRecorded")
            if event.payload["protocol_id"] == protocol_id
        ]
        if not events:
            return self._executor.initial_state(protocol)
        last = events[-1].payload
        block_ids = tuple(str(event.payload["block_id"]) for event in events)
        block_hashes = tuple(str(event.payload["block_hash"]) for event in events)
        unit_hashes = tuple(
            sorted(
                str(unit_hash)
                for event in events
                for unit_hash in event.payload["unit_hashes"]
            )
        )
        status = str(last["status"])
        reason = str(last["stop_reason"])
        return SequentialState(
            schema_version="sequential_state.v1",
            protocol_hash=protocol.protocol_hash,
            look_index=int(last["look_index"]),
            information_time=int(last["information_time"]),
            cumulative_observations=len(unit_hashes),
            used_block_ids=block_ids,
            used_block_hashes=block_hashes,
            used_unit_hashes=unit_hashes,
            support_component_log_capitals=tuple(
                float(value) for value in last["support_component_log_capitals"]
            ),
            contradiction_component_log_capitals=tuple(
                float(value)
                for value in last["contradiction_component_log_capitals"]
            ),
            support_log_evidence=float(last["cumulative_support_log_e"]),
            contradiction_log_evidence=float(last["cumulative_contradiction_log_e"]),
            status=status,  # type: ignore[arg-type]
            stop_reason=reason,  # type: ignore[arg-type]
            stopped=status != "continue",
        )


__all__ = ["SequentialFalsificationService"]
