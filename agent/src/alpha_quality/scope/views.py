"""Authorized discovery view built from a final/forward-filtered event closure."""

from __future__ import annotations

from typing import Iterable

from src.alpha_foundry.dag import FactorDAGProjector
from src.alpha_foundry.memory import EpisodicProjector, FactualMemoryView
from src.alpha_foundry.retrieval import DiscoveryEvidenceView
from src.alpha_quality.flags import ResolvedAGSFlags
from src.research_ledger.events import ResearchEventEnvelope

_DISCOVERY_SCOPES = frozenset({"train", "valid", "train_valid"})
_ALLOWED_EVENT_TYPES = frozenset(
    {
        "TrialStarted",
        "FactorDefinitionRecorded",
        "RegistryBootstrapRecorded",
        "DerivationRecorded",
        "ProcessActionFrozenV2",
        "ProcessOutcomeRecordedV2",
        "GenerationFailureRecorded",
        "EvaluationRecorded",
        "TrialTerminated",
        "FalsificationContractRegistered",
        "SequentialProtocolRegistered",
        "SequentialLookRecorded",
        "OutcomeDataAccessed",
        "FalsificationResultRecorded",
        "MechanismEvidenceIndexRecorded",
        "ComplementEvidenceRecorded",
    }
)


class DiscoveryEvidenceProjector:
    """Use official DAG/factual/episodic builders on a closed discovery stream."""

    def __init__(self, *, flags: ResolvedAGSFlags) -> None:
        if not flags.enabled("VIBE_TRADING_FACTOR_DAG"):
            raise RuntimeError("discovery evidence requires the factor DAG capability")
        if not flags.enabled("VIBE_TRADING_PROCESS_MEMORY"):
            raise RuntimeError("discovery evidence requires process memory capability")
        self.flags = flags

    def eligible_events(
        self, events: Iterable[ResearchEventEnvelope]
    ) -> tuple[ResearchEventEnvelope, ...]:
        ordered = list(events)
        evaluations = {
            event.event_hash: event
            for event in ordered
            if event.event_type == "EvaluationRecorded"
            and event.payload["data_scope"] in _DISCOVERY_SCOPES
        }
        eligible_factor_ids = {
            str(event.payload["factor_spec_id"]) for event in evaluations.values()
        }
        eligible_trial_ids = {
            str(event.payload["trial_id"]) for event in evaluations.values()
        }
        terminals = {
            event.event_hash: event
            for event in ordered
            if event.event_type == "TrialTerminated"
            and str(event.payload["trial_id"]) in eligible_trial_ids
        }
        derivations = [
            event
            for event in ordered
            if event.event_type == "DerivationRecorded"
            and str(event.payload["trial_terminal_event_hash"]) in terminals
        ]
        lineage_factor_ids = set(eligible_factor_ids)
        changed = True
        while changed:
            changed = False
            for event in derivations:
                child = str(event.payload["child_factor_spec_id"])
                if child not in lineage_factor_ids:
                    continue
                for parent in event.payload["parent_factor_spec_ids"]:
                    if str(parent) not in lineage_factor_ids:
                        lineage_factor_ids.add(str(parent))
                        changed = True
        eligible_derivation_hashes = {
            event.event_hash
            for event in derivations
            if str(event.payload["child_factor_spec_id"]) in lineage_factor_ids
        }
        eligible_outcomes = {
            event.event_hash: event
            for event in ordered
            if event.event_type == "ProcessOutcomeRecordedV2"
            and event.payload["data_scope"] in _DISCOVERY_SCOPES
            and str(event.payload["child_factor_spec_id"]) in eligible_factor_ids
            and str(event.payload["terminal_event_hash"]) in terminals
            and str(event.payload["evaluation_event_hash"]) in evaluations
            and str(event.payload["derivation_event_hash"])
            in eligible_derivation_hashes
        }
        eligible_action_ids = {
            str(event.payload["action_id"]) for event in eligible_outcomes.values()
        }
        eligible_contract_ids = {
            str(event.payload["contract_id"])
            for event in ordered
            if event.event_type == "FalsificationContractRegistered"
            and str(event.payload["factor_spec_id"]) in eligible_factor_ids
        }

        result: list[ResearchEventEnvelope] = []
        for event in ordered:
            if event.event_type not in _ALLOWED_EVENT_TYPES:
                continue
            payload = event.payload
            scope = payload.get("data_scope")
            if scope is not None and scope not in _DISCOVERY_SCOPES:
                continue
            if event.event_type == "TrialStarted" and (
                str(payload["trial_id"]) not in eligible_trial_ids
            ):
                continue
            if event.event_type == "FactorDefinitionRecorded" and (
                event.entity_id not in lineage_factor_ids
            ):
                continue
            if event.event_type == "EvaluationRecorded" and event.event_hash not in evaluations:
                continue
            if event.event_type == "TrialTerminated" and event.event_hash not in terminals:
                continue
            if event.event_type == "DerivationRecorded" and (
                event.event_hash not in eligible_derivation_hashes
            ):
                continue
            if event.event_type == "ProcessActionFrozenV2" and (
                event.entity_id not in eligible_action_ids
            ):
                continue
            if event.event_type == "ProcessOutcomeRecordedV2" and (
                event.event_hash not in eligible_outcomes
            ):
                continue
            if event.event_type == "FalsificationContractRegistered" and (
                str(payload["contract_id"]) not in eligible_contract_ids
            ):
                continue
            if event.event_type in {
                "SequentialProtocolRegistered",
                "FalsificationResultRecorded",
            } and str(payload["contract_id"]) not in eligible_contract_ids:
                continue
            if event.event_type in {
                "SequentialLookRecorded",
                "OutcomeDataAccessed",
            } and str(payload["factor_spec_id"]) not in eligible_factor_ids:
                continue
            if event.event_type in {
                "MechanismEvidenceIndexRecorded",
                "ComplementEvidenceRecorded",
            } and str(payload["factor_spec_id"]) not in eligible_factor_ids:
                continue
            result.append(event)
        return tuple(result)

    def factual_view(
        self, events: Iterable[ResearchEventEnvelope]
    ) -> FactualMemoryView:
        eligible = self.eligible_events(events)
        dag = FactorDAGProjector(flags=self.flags).project(eligible)
        return FactualMemoryView.from_terminal_discovery_events(dag, eligible)

    def project(
        self,
        events: Iterable[ResearchEventEnvelope],
        *,
        data_snapshot_hash: str,
    ) -> DiscoveryEvidenceView:
        eligible = self.eligible_events(events)
        if not eligible:
            raise ValueError("no terminal train/valid discovery evidence is available")
        dag = FactorDAGProjector(flags=self.flags).project(eligible)
        episodic = EpisodicProjector().project(eligible)
        factual = FactualMemoryView.from_terminal_discovery_events(dag, eligible)
        return DiscoveryEvidenceView.from_terminal_views(
            factual=factual,
            episodic=episodic,
            data_snapshot_hash=data_snapshot_hash,
        )


__all__ = ["DiscoveryEvidenceProjector"]
