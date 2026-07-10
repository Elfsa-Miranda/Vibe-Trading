"""Runtime-enforced one-shot final-test capability authority."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import uuid4

from src.alpha_quality.final_test.model import (
    FinalTestAccessAudit,
    FinalTestDataRequest,
    FrozenFinalCandidate,
)
from src.alpha_quality.flags import ResolvedAGSFlags
from src.research_ledger.events import EventDraft, EventTransitionError, ResearchEventStore
from src.research_ledger.hash_utils import canonical_json_hash, utc_now_iso


class FinalScopeViolation(RuntimeError):
    """A prohibited final-data request; no data provider may be called."""


@dataclass(frozen=True)
class TestScopeCapability:
    token_id: str
    token_hash: str
    candidate_hash: str
    factor_spec_id: str
    declared_run_id: str
    data_snapshot_hash: str
    period_start: str
    period_end: str
    allowed_fields: tuple[str, ...]
    issued_at: str
    scope: Literal["test"] = "test"


@dataclass
class _CapabilityState:
    capability: TestScopeCapability
    consumed: bool = False


class TestScopeAuthority:
    __test__ = False

    def __init__(
        self,
        *,
        store: ResearchEventStore,
        flags: ResolvedAGSFlags,
    ) -> None:
        if not flags.enabled("VIBE_TRADING_DECISION_V2"):
            raise RuntimeError("final-test capability is disabled")
        self.store = store
        self._states: dict[str, _CapabilityState] = {}
        self._tainted_candidates: set[str] = set()

    def issue(
        self,
        candidate: FrozenFinalCandidate,
        *,
        run_id: str,
        period_start: str,
        period_end: str,
        allowed_fields: tuple[str, ...] = ("net_returns", "rank_ic_series"),
    ) -> TestScopeCapability:
        if not isinstance(candidate, FrozenFinalCandidate):
            raise TypeError("a frozen final candidate is required")
        if period_end < period_start or allowed_fields != tuple(sorted(set(allowed_fields))):
            raise ValueError("invalid frozen final scope")
        definitions = self.store.query_events(
            event_type="FactorDefinitionRecorded", entity_id=candidate.factor_spec_id
        )
        if not definitions:
            raise FinalScopeViolation("final access requires a prior frozen factor definition")
        if candidate.definition_hash != definitions[-1].event_hash:
            raise FinalScopeViolation("frozen definition hash does not match ledger authority")
        prior_issues = [
            event
            for event in self.store.query_events(event_type="FinalTestCapabilityIssued")
            if event.payload["candidate_hash"] == candidate.candidate_hash
        ]
        if prior_issues:
            self._tainted_candidates.add(candidate.candidate_hash)
            prior = prior_issues[-1].payload
            request_hash = canonical_json_hash(
                {
                    "candidate_hash": candidate.candidate_hash,
                    "attempted_run_id": run_id,
                    "period_start": period_start,
                    "period_end": period_end,
                    "allowed_fields": list(allowed_fields),
                }
            )
            access_id = "final-access-" + str(uuid4())
            self.store.append_event(
                EventDraft(
                    event_type="FinalTestAccessRecorded",
                    entity_id=access_id,
                    run_id=run_id,
                    payload_schema_version="final_test_access_recorded.v1",
                    payload={
                        "access_id": access_id,
                        "capability_fingerprint": prior["capability_fingerprint"],
                        "candidate_hash": candidate.candidate_hash,
                        "factor_spec_id": candidate.factor_spec_id,
                        "declared_run_id": prior["declared_run_id"],
                        "request_hash": request_hash,
                        "outcome": "denied",
                        "reason_code": "REPEATED_FINAL_CAPABILITY_ISSUANCE",
                        "contaminated": True,
                        "accessed_at": utc_now_iso(),
                    },
                )
            )
            raise FinalScopeViolation("a frozen candidate can receive only one final capability")
        if self.is_tainted(candidate.candidate_hash):
            raise FinalScopeViolation("contaminated candidate cannot receive final capability")

        freeze_id = "final-freeze-" + candidate.candidate_hash.removeprefix("sha256:")[:24]
        self.store.append_event(
            EventDraft(
                event_type="FinalCandidateFrozen",
                entity_id=freeze_id,
                run_id=run_id,
                payload_schema_version="final_candidate_frozen.v1",
                idempotency_key="final-freeze:" + candidate.candidate_hash,
                payload={
                    "freeze_id": freeze_id,
                    "candidate_schema_version": candidate.schema_version,
                    "factor_spec_id": candidate.factor_spec_id,
                    "definition_hash": candidate.definition_hash,
                    "transform_pipeline_hash": candidate.transform_pipeline_hash,
                    "cost_model_hash": candidate.cost_model_hash,
                    "regime_config_hash": candidate.regime_config_hash,
                    "policy_hash": candidate.policy_hash,
                    "data_snapshot_hash": candidate.data_snapshot_hash,
                    "frozen_at": candidate.frozen_at,
                    "candidate_hash": candidate.candidate_hash,
                },
            )
        )
        token_id = str(uuid4())
        token_hash = canonical_json_hash({"token_id": token_id})
        issued_at = utc_now_iso()
        capability = TestScopeCapability(
            token_id=token_id,
            token_hash=token_hash,
            candidate_hash=candidate.candidate_hash,
            factor_spec_id=candidate.factor_spec_id,
            declared_run_id=run_id,
            data_snapshot_hash=candidate.data_snapshot_hash,
            period_start=period_start,
            period_end=period_end,
            allowed_fields=allowed_fields,
            issued_at=issued_at,
        )
        capability_id = "final-capability-" + token_hash.removeprefix("sha256:")[:24]
        try:
            self.store.append_event(
                EventDraft(
                    event_type="FinalTestCapabilityIssued",
                    entity_id=capability_id,
                    run_id=run_id,
                    payload_schema_version="final_test_capability_issued.v1",
                    idempotency_key="final-capability:" + token_hash,
                    payload={
                        "capability_id": capability_id,
                        "capability_fingerprint": token_hash,
                        "candidate_hash": candidate.candidate_hash,
                        "factor_spec_id": candidate.factor_spec_id,
                        "declared_run_id": run_id,
                        "data_snapshot_hash": candidate.data_snapshot_hash,
                        "period_start": period_start,
                        "period_end": period_end,
                        "allowed_fields": list(allowed_fields),
                        "issued_at": issued_at,
                    },
                )
            )
        except EventTransitionError as exc:
            concurrent = [
                event
                for event in self.store.query_events(event_type="FinalTestCapabilityIssued")
                if event.payload["candidate_hash"] == candidate.candidate_hash
            ]
            if concurrent:
                self._tainted_candidates.add(candidate.candidate_hash)
                prior = concurrent[-1].payload
                access_id = "final-access-" + str(uuid4())
                self.store.append_event(
                    EventDraft(
                        event_type="FinalTestAccessRecorded",
                        entity_id=access_id,
                        run_id=run_id,
                        payload_schema_version="final_test_access_recorded.v1",
                        payload={
                            "access_id": access_id,
                            "capability_fingerprint": prior[
                                "capability_fingerprint"
                            ],
                            "candidate_hash": candidate.candidate_hash,
                            "factor_spec_id": candidate.factor_spec_id,
                            "declared_run_id": prior["declared_run_id"],
                            "request_hash": canonical_json_hash(
                                {
                                    "candidate_hash": candidate.candidate_hash,
                                    "attempted_run_id": run_id,
                                    "period_start": period_start,
                                    "period_end": period_end,
                                    "allowed_fields": list(allowed_fields),
                                }
                            ),
                            "outcome": "denied",
                            "reason_code": "CONCURRENT_FINAL_CAPABILITY_ISSUANCE",
                            "contaminated": True,
                            "accessed_at": utc_now_iso(),
                        },
                    )
                )
                raise FinalScopeViolation(
                    "concurrent final capability issuance contaminated the candidate"
                ) from exc
            raise
        self._states[token_id] = _CapabilityState(capability=capability)
        return capability

    def authorize(
        self,
        capability: TestScopeCapability,
        request: FinalTestDataRequest,
    ) -> FinalTestAccessAudit:
        state = self._states.get(capability.token_id)
        reason = self._violation_reason(state, capability, request)
        if reason is not None:
            candidate_hash = (
                request.candidate_hash if state is None else state.capability.candidate_hash
            )
            self._tainted_candidates.add(candidate_hash)
            if state is not None:
                state.consumed = True
            self._record_access(
                capability=capability,
                request=request,
                outcome="denied",
                reason_code=reason,
                contaminated=True,
            )
            raise FinalScopeViolation(f"final access denied before data return: {reason}")

        assert state is not None
        state.consumed = True
        return self._record_access(
            capability=capability,
            request=request,
            outcome="allowed",
            reason_code="FINAL_ACCESS_ALLOWED_ONCE",
            contaminated=self.is_tainted(capability.candidate_hash),
        )

    @staticmethod
    def _violation_reason(
        state: _CapabilityState | None,
        supplied: TestScopeCapability,
        request: FinalTestDataRequest,
    ) -> str | None:
        if state is None:
            return "UNKNOWN_OR_FORGED_CAPABILITY"
        expected = state.capability
        if supplied != expected:
            return "MISMATCHED_CAPABILITY"
        if state.consumed:
            return "REPEATED_FINAL_ACCESS"
        if request.run_id != expected.declared_run_id:
            return "MISMATCHED_FINAL_RUN"
        if request.factor_spec_id != expected.factor_spec_id:
            return "MISMATCHED_FINAL_FACTOR"
        if request.candidate_hash != expected.candidate_hash:
            return "MISMATCHED_FROZEN_CANDIDATE"
        if request.data_snapshot_hash != expected.data_snapshot_hash:
            return "MISMATCHED_FINAL_SNAPSHOT"
        if request.period_start < expected.period_start or request.period_end > expected.period_end:
            return "WIDENED_FINAL_PERIOD"
        if not set(request.fields).issubset(expected.allowed_fields):
            return "WIDENED_FINAL_FIELDS"
        return None

    def _record_access(
        self,
        *,
        capability: TestScopeCapability,
        request: FinalTestDataRequest,
        outcome: Literal["allowed", "denied"],
        reason_code: str,
        contaminated: bool,
    ) -> FinalTestAccessAudit:
        accessed_at = utc_now_iso()
        access_id = "final-access-" + str(uuid4())
        event = self.store.append_event(
            EventDraft(
                event_type="FinalTestAccessRecorded",
                entity_id=access_id,
                run_id=request.run_id,
                payload_schema_version="final_test_access_recorded.v1",
                payload={
                    "access_id": access_id,
                    "capability_fingerprint": capability.token_hash,
                    "candidate_hash": request.candidate_hash,
                    "factor_spec_id": request.factor_spec_id,
                    "declared_run_id": capability.declared_run_id,
                    "request_hash": request.request_hash,
                    "outcome": outcome,
                    "reason_code": reason_code,
                    "contaminated": contaminated,
                    "accessed_at": accessed_at,
                },
            )
        )
        return FinalTestAccessAudit(
            access_event_hash=event.event_hash,
            request_hash=request.request_hash,
            outcome=outcome,
            reason_code=reason_code,
            contaminated=contaminated,
            accessed_at=accessed_at,
        )

    def is_tainted(self, candidate_hash: str) -> bool:
        if candidate_hash in self._tainted_candidates:
            return True
        return any(
            event.payload["candidate_hash"] == candidate_hash
            and event.payload["contaminated"]
            for event in self.store.query_events(event_type="FinalTestAccessRecorded")
        )

    def contaminate_after_access(
        self,
        capability: TestScopeCapability,
        request: FinalTestDataRequest,
        *,
        reason_code: str,
    ) -> FinalTestAccessAudit:
        self._tainted_candidates.add(request.candidate_hash)
        return self._record_access(
            capability=capability,
            request=request,
            outcome="denied",
            reason_code=reason_code,
            contaminated=True,
        )

    def audit_trail(self, candidate_hash: str) -> tuple[FinalTestAccessAudit, ...]:
        return tuple(
            FinalTestAccessAudit(
                access_event_hash=event.event_hash,
                request_hash=str(event.payload["request_hash"]),
                outcome=event.payload["outcome"],  # type: ignore[arg-type]
                reason_code=str(event.payload["reason_code"]),
                contaminated=bool(event.payload["contaminated"]),
                accessed_at=str(event.payload["accessed_at"]),
            )
            for event in self.store.query_events(event_type="FinalTestAccessRecorded")
            if event.payload["candidate_hash"] == candidate_hash
        )


__all__ = ["FinalScopeViolation", "TestScopeAuthority", "TestScopeCapability"]
