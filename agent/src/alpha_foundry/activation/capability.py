"""Research-only active retriever capability, gated by immutable evidence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping

from src.alpha_foundry.activation.artifacts import ActivationArtifactStore
from src.alpha_quality.flags import ResolvedAGSFlags
from src.research_ledger.events import ResearchEventStore


@dataclass(frozen=True)
class ActivationCompatibility:
    code_hash: str
    generator_hash: str
    grammar_hash: str
    treatment_policy_hash: str
    decision_policy_hash: str
    train_snapshot_hash: str
    valid_snapshot_hash: str


@dataclass(frozen=True)
class RetrieverModeResolution:
    mode: Literal["flat", "shadow", "active_research_only"]
    reason: str
    decision_hash: str | None = None


class ActiveRetrieverCapability:
    """Resolve candidate order only; this object has no quality or live-trading API."""

    def __init__(self, resolution: RetrieverModeResolution) -> None:
        if resolution.mode != "active_research_only":
            raise TypeError("active retriever capability requires approved compatible evidence")
        self.resolution = resolution

    def choose(
        self,
        *,
        flat_candidate_ids: tuple[str, ...],
        topology_candidate_ids: tuple[str, ...],
    ) -> tuple[str, ...]:
        if len(topology_candidate_ids) != len(set(topology_candidate_ids)):
            raise ValueError("topology candidates must be unique")
        return topology_candidate_ids


class ActiveRetrieverResolver:
    def __init__(
        self,
        artifact_store: ActivationArtifactStore,
        *,
        event_store: ResearchEventStore | None = None,
    ) -> None:
        self.artifact_store = artifact_store
        self.event_store = event_store

    def resolve(
        self,
        *,
        flags: ResolvedAGSFlags,
        plan_hash: str | None,
        result_hash: str | None,
        decision_hash: str | None,
        compatibility: ActivationCompatibility,
    ) -> RetrieverModeResolution:
        required_shadow = (
            "VIBE_TRADING_ALPHA_FOUNDRY",
            "VIBE_TRADING_RESEARCH_EVENTS",
            "VIBE_TRADING_FACTOR_DAG",
            "VIBE_TRADING_PROCESS_MEMORY",
            "VIBE_TRADING_TOPOLOGY_RETRIEVER",
        )
        if any(not flags.enabled(name) for name in required_shadow):
            return RetrieverModeResolution("flat", "TOPOLOGY_RETRIEVER_DISABLED")
        if not flags.enabled("VIBE_TRADING_TOPOLOGY_RETRIEVER_ACTIVE"):
            return RetrieverModeResolution("shadow", "ACTIVE_CAPABILITY_DISABLED")
        if not plan_hash or not result_hash or not decision_hash:
            return RetrieverModeResolution("shadow", "APPROVED_ARTIFACT_SET_MISSING")
        try:
            plan = self.artifact_store.get("plan", plan_hash)
            result = self.artifact_store.get("result", result_hash)
            decision = self.artifact_store.get("decision", decision_hash)
        except (OSError, TypeError, ValueError):
            return RetrieverModeResolution("shadow", "ACTIVATION_ARTIFACT_INVALID")
        if decision.get("verdict") != "approved" or decision.get("active_research_only") is not True:
            return RetrieverModeResolution("shadow", "ACTIVATION_NOT_APPROVED", decision_hash)
        if decision.get("plan_hash") != plan_hash or decision.get("result_hash") != result_hash:
            return RetrieverModeResolution("shadow", "ACTIVATION_ARTIFACT_LINK_MISMATCH", decision_hash)
        if result.get("plan_hash") != plan_hash or result.get("replayable") is not True:
            return RetrieverModeResolution("shadow", "ACTIVATION_RESULT_NOT_REPLAYABLE", decision_hash)
        if result.get("invalidation_reasons"):
            return RetrieverModeResolution("shadow", "ACTIVATION_RESULT_INVALIDATED", decision_hash)
        if self.event_store is None or not self.event_store.verify_chain():
            return RetrieverModeResolution("shadow", "ACTIVATION_LEDGER_AUTHORITY_MISSING", decision_hash)
        evidence = self.event_store.query_events()
        required_events = {
            "ActivationPlanRegistered": plan_hash,
            "ActivationResultRecorded": result_hash,
            "RetrieverActivationDecisionRecorded": decision_hash,
        }
        for event_type, expected_hash in required_events.items():
            hash_field = {
                "ActivationPlanRegistered": "plan_hash",
                "ActivationResultRecorded": "result_hash",
                "RetrieverActivationDecisionRecorded": "decision_hash",
            }[event_type]
            if not any(
                event.event_type == event_type
                and event.payload.get(hash_field) == expected_hash
                for event in evidence
            ):
                return RetrieverModeResolution("shadow", "ACTIVATION_LEDGER_EVIDENCE_MISSING", decision_hash)
        if not self._approval_replays(plan, result, decision):
            return RetrieverModeResolution("shadow", "ACTIVATION_DECISION_REPLAY_FAILED", decision_hash)
        provenance = plan.get("provenance")
        if not isinstance(provenance, Mapping):
            return RetrieverModeResolution("shadow", "ACTIVATION_PROVENANCE_MISSING", decision_hash)
        expected = {
            "code_hash": compatibility.code_hash,
            "generator_hash": compatibility.generator_hash,
            "grammar_hash": compatibility.grammar_hash,
            "treatment_policy_hash": compatibility.treatment_policy_hash,
            "train_snapshot_hash": compatibility.train_snapshot_hash,
            "valid_snapshot_hash": compatibility.valid_snapshot_hash,
        }
        if any(provenance.get(name) != value for name, value in expected.items()):
            return RetrieverModeResolution("shadow", "ACTIVATION_PROVENANCE_MISMATCH", decision_hash)
        if decision.get("policy_hash") != compatibility.decision_policy_hash:
            return RetrieverModeResolution("shadow", "ACTIVATION_POLICY_MISMATCH", decision_hash)
        return RetrieverModeResolution("active_research_only", "APPROVED_COMPATIBLE", decision_hash)

    @staticmethod
    def _approval_replays(
        plan: Mapping[str, object],
        result: Mapping[str, object],
        decision: Mapping[str, object],
    ) -> bool:
        analysis = plan.get("analysis")
        primary = result.get("primary_effect")
        noninferiority = result.get("noninferiority_results")
        propensity = result.get("propensity_diagnostics")
        coverage = result.get("coverage_diagnostics")
        if not all(
            isinstance(item, Mapping)
            for item in (analysis, primary, noninferiority, propensity, coverage)
        ):
            return False
        assert isinstance(analysis, Mapping)
        assert isinstance(primary, Mapping)
        assert isinstance(noninferiority, Mapping)
        assert isinstance(propensity, Mapping)
        assert isinstance(coverage, Mapping)
        family = analysis.get("multiple_testing_family")
        if not isinstance(family, list):
            return False
        try:
            enough_pairs = int(str(result["complete_pairs"])) >= max(
                int(str(analysis["minimum_effective_pairs"])),
                int(str(analysis["required_independent_groups"])),
            )
            resolved_primary = (
                float(str(primary["ci_lower"])) > float(str(analysis["primary_threshold"]))
                and float(str(primary["ci_upper"])) - float(str(primary["ci_lower"]))
                <= float(str(analysis["maximum_ci_width"]))
            )
            secondaries_pass = all(noninferiority.get(str(name)) is True for name in family)
            diagnostics_pass = (
                float(str(propensity.get("unexplained_fraction", 1.0))) == 0.0
                and float(str(coverage.get("coverage_collapse", 1.0))) == 0.0
            )
        except (KeyError, TypeError, ValueError):
            return False
        return bool(
            enough_pairs
            and resolved_primary
            and secondaries_pass
            and diagnostics_pass
            and result.get("power_limitation") is None
            and result.get("replayable") is True
            and not result.get("invalidation_reasons")
            and decision.get("verdict") == "approved"
            and decision.get("active_research_only") is True
            and decision.get("reasons") == ["ALL_PREREGISTERED_GATES_PASSED"]
        )


__all__ = [
    "ActivationCompatibility", "ActiveRetrieverCapability", "ActiveRetrieverResolver",
    "RetrieverModeResolution",
]
