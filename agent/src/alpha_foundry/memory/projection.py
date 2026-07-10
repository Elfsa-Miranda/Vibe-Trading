"""Replayable episodic process-memory projection from closed typed events."""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from src.alpha_foundry.dsl.diff import ast_diff_from_dict
from src.alpha_foundry.memory.model import EpisodicProjection, ProcessMemoryObservation, ProcessPosterior
from src.alpha_foundry.memory.motif import derive_motif
from src.research_ledger.events import ResearchEventEnvelope
from src.research_ledger.hash_utils import canonical_json_hash


class EpisodicProjector:
    def __init__(self, *, minimum_effective_count: int = 3, max_positive_adjustment: float = 0.25, negative_veto_threshold: float = -0.2) -> None:
        if minimum_effective_count < 1 or max_positive_adjustment < 0:
            raise ValueError("invalid episodic memory policy")
        self.minimum_effective_count = minimum_effective_count
        self.max_positive_adjustment = max_positive_adjustment
        self.negative_veto_threshold = negative_veto_threshold

    def project(self, events: Iterable[ResearchEventEnvelope]) -> EpisodicProjection:
        ordered = list(events)
        actions = {event.entity_id: event for event in ordered if event.event_type == "ProcessActionFrozen"}
        terminals = {event.event_hash: event for event in ordered if event.event_type == "TrialTerminated"}
        derivations = {
            str(event.payload["child_factor_spec_id"]): event
            for event in ordered
            if event.event_type == "DerivationRecorded"
        }
        observations: list[ProcessMemoryObservation] = []
        for event in ordered:
            if event.event_type != "ProcessOutcomeRecorded":
                continue
            payload = event.payload
            if payload["data_scope"] not in {"train", "valid", "train_valid"}:
                continue
            child = payload["child_factor_spec_id"]
            raw_diff = payload["ast_diff"]
            observed = payload["observed_validation_utility"]
            if child is None or raw_diff is None or observed is None:
                # Invalid/unparsable outputs have a terminal event but never a
                # fake child or motif observation.
                continue
            action = actions.get(str(payload["action_id"]))
            terminal = terminals.get(str(payload["terminal_event_hash"]))
            derivation = derivations.get(str(child))
            if action is None or terminal is None or derivation is None:
                continue
            if derivation.payload["trial_terminal_event_hash"] != terminal.event_hash:
                continue
            diff = ast_diff_from_dict(raw_diff)
            motif = derive_motif(diff)
            action_payload = action.payload
            base = float(action_payload["base_expected_utility"])
            utility = float(observed)
            context = canonical_json_hash(
                {
                    "parent_factor_spec_id": action_payload["parent_factor_spec_id"],
                    "policy_hash": action_payload["policy_hash"],
                    "eligible_event_watermark": action_payload["eligible_event_watermark"],
                }
            )
            observations.append(
                ProcessMemoryObservation(
                    parent_context_hash=context,
                    parent_factor_spec_id=str(action_payload["parent_factor_spec_id"]),
                    child_factor_spec_id=str(child),
                    derivation_event_hash=derivation.event_hash,
                    ast_diff_hash=motif.ast_diff_hash,
                    motif_version=motif.motif_version,
                    motif=motif.motif,
                    base_expected_utility=base,
                    observed_validation_utility=utility,
                    residual=utility - base,
                    terminal_status=str(terminal.payload["status"]),
                    failure_codes=tuple(str(code) for code in terminal.payload["reason_codes"]),
                    regime_config_hash=None,
                    policy_hash=str(action_payload["policy_hash"]),
                    available_at=str(payload["available_at"]),
                )
            )
        posteriors = self._posteriors(observations)
        state = {
            "schema_version": "episodic_process_projection.v1",
            "source_event_hashes": [event.event_hash for event in ordered],
            "observations": [observation.__dict__ for observation in observations],
            "posteriors": [posterior.__dict__ for posterior in posteriors],
        }
        return EpisodicProjection(
            schema_version="episodic_process_projection.v1",
            source_watermark_event_hash=ordered[-1].event_hash if ordered else None,
            observations=tuple(observations),
            posteriors=tuple(posteriors),
            projection_hash=canonical_json_hash(state),
        )

    def _posteriors(self, observations: list[ProcessMemoryObservation]) -> list[ProcessPosterior]:
        grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
        for observation in observations:
            if observation.residual is not None:
                grouped[(observation.parent_context_hash, observation.motif)].append(observation.residual)
        result: list[ProcessPosterior] = []
        for (context, motif), values in sorted(grouped.items()):
            count = len(values)
            mean = sum(values) / count
            confidence = min(1.0, count / self.minimum_effective_count)
            positive = min(self.max_positive_adjustment, max(0.0, mean) * confidence)
            hard_veto = count >= self.minimum_effective_count and confidence >= 1.0 and mean <= self.negative_veto_threshold
            result.append(ProcessPosterior(context, motif, count, mean, confidence, positive, hard_veto))
        return result


__all__ = ["EpisodicProjector"]
