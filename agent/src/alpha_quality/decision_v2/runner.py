"""Deterministic non-compensatory Decision v2 tier lattice."""

from __future__ import annotations

from typing import Any, cast

from src.alpha_quality.decision_v2.model import (
    AlphaQualityDecisionV2,
    DecisionEvidenceRecord,
    DecisionEvidenceRefs,
    DecisionLevel,
    EvidenceKind,
)
from src.alpha_quality.decision_v2.policy import DecisionV2Policy
from src.alpha_quality.decision_v2.repository import (
    DecisionEvidenceRepository,
    EvidenceResolutionError,
)
from src.alpha_quality.flags import ResolvedAGSFlags
from src.research_ledger.hash_utils import canonical_json_hash


class QualityDecisionV2Runner:
    def __init__(
        self,
        *,
        flags: ResolvedAGSFlags,
        policy: DecisionV2Policy,
        repository: DecisionEvidenceRepository,
    ) -> None:
        if not flags.enabled("VIBE_TRADING_DECISION_V2"):
            raise RuntimeError("Decision v2 capability is disabled")
        self.policy = policy
        self.repository = repository

    def run(self, refs: DecisionEvidenceRefs) -> AlphaQualityDecisionV2:
        if not isinstance(refs, DecisionEvidenceRefs):
            raise TypeError("Decision v2 accepts only typed immutable evidence references")

        records: dict[EvidenceKind, DecisionEvidenceRecord] = {}
        caps: set[str] = set()
        reasons: set[str] = set()
        warnings: set[str] = set()
        limitations: set[str] = set()

        self._resolve_required(records, caps, refs, "scorecard", refs.scorecard_hash)
        self._resolve_required(records, caps, refs, "ledger", refs.ledger_watermark_hash)
        self._resolve_optional(
            records,
            caps,
            refs,
            "execution",
            refs.execution_hash,
            required=self.policy.require_execution,
            missing_code="EXECUTION_EVIDENCE_MISSING",
        )
        self._resolve_optional(
            records,
            caps,
            refs,
            "snapshot",
            refs.snapshot_hash,
            required=self.policy.require_snapshot,
            missing_code="PIT_SNAPSHOT_MISSING",
        )
        self._resolve_optional(
            records,
            caps,
            refs,
            "mechanism",
            refs.mechanism_evidence_hash,
            required=self.policy.require_mechanism,
            missing_code="MECHANISM_EVIDENCE_MISSING",
        )
        self._resolve_optional(
            records,
            caps,
            refs,
            "complement",
            refs.complement_evidence_hash,
            required=self.policy.require_complement,
            missing_code="COMPLEMENT_EVIDENCE_MISSING",
        )
        self._resolve_optional(
            records,
            caps,
            refs,
            "final_test",
            refs.final_test_artifact_hash,
            required=False,
            missing_code="",
        )
        self._resolve_optional(
            records,
            caps,
            refs,
            "forward_plan",
            refs.forward_plan_hash,
            required=False,
            missing_code="",
        )

        for record in records.values():
            limitations.update(str(item) for item in record.payload["limitations"])

        scorecard = self._payload(records, "scorecard")
        if scorecard is not None:
            if not scorecard["formula_valid"]:
                reasons.add("INVALID_FORMULA")
            if scorecard["formula_ambiguous"]:
                reasons.add("AMBIGUOUS_FORMULA")
            if scorecard["lookahead_detected"]:
                reasons.add("LOOKAHEAD_DETECTED")
            if not scorecard["train_valid_terminal"]:
                caps.add("TERMINAL_TRAIN_VALID_EVIDENCE_MISSING")
            if not scorecard["reproducible"]:
                caps.add("NON_REPRODUCIBLE_EVIDENCE")
            if not scorecard["bounded"]:
                caps.add("SAMPLE_OR_BOUNDS_INCOMPLETE")
            if scorecard["regime_dependent"]:
                warnings.add("REGIME_DEPENDENT")

        ledger = self._payload(records, "ledger")
        if ledger is not None:
            if not ledger["complete"]:
                caps.add("LEDGER_EVIDENCE_INCOMPLETE")
            if not ledger["terminal_train_valid"]:
                caps.add("TERMINAL_TRAIN_VALID_EVIDENCE_MISSING")
            if ledger["reduced_durability"]:
                caps.add("REDUCED_DURABILITY")
            if ledger.get("ledger_schema_version") != "decision_ledger_evidence.v2":
                caps.add("LEGACY_LEDGER_INFRASTRUCTURE_STATUS_UNVERIFIED")
            elif ledger["infrastructure_failure_event_hashes"]:
                caps.add("INFRASTRUCTURE_FAILURE")

        snapshot = self._payload(records, "snapshot")
        if snapshot is not None:
            if not snapshot["pit_available"]:
                caps.add("PIT_SNAPSHOT_MISSING")
            if snapshot["survivorship_bias"]:
                caps.add("SURVIVORSHIP_BIAS")

        execution = self._payload(records, "execution")
        if execution is not None:
            if not execution["available"]:
                caps.add("EXECUTION_EVIDENCE_MISSING")
            else:
                alpha = float(execution["execution_alpha"])
                cost = float(execution["total_cost"])
                if cost > alpha:
                    reasons.add("COST_EXCEEDS_EXECUTION_ALPHA")
                elif execution["economically_nonnegative"] is not True:
                    caps.add("EXECUTION_ECONOMICS_NEGATIVE")

        mechanism = self._payload(records, "mechanism")
        if mechanism is not None:
            if not mechanism["contract_registered"]:
                caps.add("MECHANISM_CONTRACT_MISSING")
            if not mechanism["decisive_available"] or mechanism["ordinal_state"] == "inconclusive":
                caps.add("MECHANISM_EVIDENCE_INCONCLUSIVE")
            if mechanism["ordinal_state"] == "falsified":
                caps.add("MECHANISM_FALSIFIED")

        complement = self._payload(records, "complement")
        if complement is not None:
            status = complement["status"]
            if status == "duplicate":
                reasons.add("DUPLICATE_IDENTITY")
            elif status in {"unavailable", "insufficient"}:
                caps.add("COMPLEMENT_EVIDENCE_UNAVAILABLE")
            elif status == "nonpositive_marginal_value":
                caps.add("COMPLEMENT_NET_VALUE_NONPOSITIVE")

        final_test = self._payload(records, "final_test")
        if final_test is not None and final_test["contaminated"]:
            reasons.add("FINAL_TEST_CONTAMINATED")

        within_tier_score = self._within_tier_score(scorecard, execution)
        decision: DecisionLevel
        if reasons:
            decision = "reject"
        elif caps:
            decision = "research_only"
        else:
            decision = "candidate_zoo"
            reasons.add("TERMINAL_TRAIN_VALID_EVIDENCE_QUALIFIED")
            if final_test is not None:
                if (
                    final_test["frozen"]
                    and final_test["one_shot"]
                    and not final_test["contaminated"]
                    and final_test["quality_passed"]
                ):
                    decision = "paper_candidate"
                    reasons.add("FROZEN_FINAL_TEST_QUALIFIED")
                else:
                    warnings.add("FINAL_TEST_DID_NOT_PASS_FROZEN_QUALITY")
            forward_plan = self._payload(records, "forward_plan")
            if forward_plan is not None:
                if decision == "paper_candidate" and forward_plan["frozen"]:
                    decision = "forward_track"
                    reasons.add("FROZEN_FORWARD_PLAN_QUALIFIED")
                    warnings.add("FORWARD_TRACKING_STARTED_NO_SUCCESS_CLAIM")
                else:
                    warnings.add("FORWARD_PLAN_INELIGIBLE")

        tier = {
            "reject": 0,
            "research_only": 1,
            "candidate_zoo": 2,
            "paper_candidate": 3,
            "forward_track": 4,
        }[decision]
        content: dict[str, Any] = {
            "schema_version": "alpha_quality_decision.v2",
            "factor_spec_id": refs.factor_spec_id,
            "decision": decision,
            "tier": tier,
            "policy_version": self.policy.policy_version,
            "policy_hash": self.policy.policy_hash,
            "evidence_hashes": list(refs.evidence_hashes),
            "reasons": sorted(reasons),
            "warnings": sorted(warnings),
            "caps": sorted(caps),
            "limitations": sorted(limitations),
            "within_tier_score": within_tier_score,
            "forward_success_claim": False,
        }
        return AlphaQualityDecisionV2(
            schema_version="alpha_quality_decision.v2",
            factor_spec_id=refs.factor_spec_id,
            decision=decision,
            tier=tier,
            policy_version=self.policy.policy_version,
            policy_hash=self.policy.policy_hash,
            evidence_hashes=refs.evidence_hashes,
            reasons=tuple(sorted(reasons)),
            warnings=tuple(sorted(warnings)),
            caps=tuple(sorted(caps)),
            limitations=tuple(sorted(limitations)),
            within_tier_score=within_tier_score,
            forward_success_claim=False,
            decision_hash=canonical_json_hash(content),
        )

    def _resolve_required(
        self,
        records: dict[EvidenceKind, DecisionEvidenceRecord],
        caps: set[str],
        refs: DecisionEvidenceRefs,
        kind: EvidenceKind,
        evidence_hash: str,
    ) -> None:
        try:
            records[kind] = self.repository.resolve(
                evidence_hash, expected_kind=kind, factor_spec_id=refs.factor_spec_id
            )
        except EvidenceResolutionError:
            caps.add("EVIDENCE_REFERENCE_UNRESOLVED")

    def _resolve_optional(
        self,
        records: dict[EvidenceKind, DecisionEvidenceRecord],
        caps: set[str],
        refs: DecisionEvidenceRefs,
        kind: EvidenceKind,
        evidence_hash: str | None,
        *,
        required: bool,
        missing_code: str,
    ) -> None:
        if evidence_hash is None:
            if required:
                caps.add(missing_code)
            return
        self._resolve_required(records, caps, refs, kind, evidence_hash)

    @staticmethod
    def _payload(
        records: dict[EvidenceKind, DecisionEvidenceRecord], kind: EvidenceKind
    ) -> dict[str, Any] | None:
        record = records.get(kind)
        return None if record is None else cast(dict[str, Any], dict(record.payload))

    def _within_tier_score(
        self,
        scorecard: dict[str, Any] | None,
        execution: dict[str, Any] | None,
    ) -> float:
        rank_component = 0.0
        if scorecard is not None and scorecard["validation_rank_ic"] is not None:
            rank_component = max(
                -1.0,
                min(1.0, float(scorecard["validation_rank_ic"]) / self.policy.rank_ic_score_scale),
            )
        economic_component = 0.0
        if execution is not None and execution["available"]:
            alpha = abs(float(execution["execution_alpha"]))
            margin = float(execution["execution_alpha"]) - float(execution["total_cost"])
            economic_component = max(-1.0, min(1.0, margin / max(alpha, 1e-12)))
        return round((rank_component + economic_component) / 2.0, 12)


__all__ = ["QualityDecisionV2Runner"]
