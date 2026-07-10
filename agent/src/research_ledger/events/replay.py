"""Deterministic replay projection for research-event integrity checks."""

from __future__ import annotations

from collections import Counter
from typing import Iterable

from src.research_ledger.events.model import ReplayState, ResearchEventEnvelope
from src.research_ledger.hash_utils import canonical_json_hash


def build_replay_state(events: Iterable[ResearchEventEnvelope]) -> ReplayState:
    ordered = list(events)
    event_types = Counter(event.event_type for event in ordered)
    started: set[str] = set()
    terminals: dict[str, str] = {}
    for event in ordered:
        if event.event_type == "TrialStarted":
            started.add(str(event.payload["trial_id"]))
        elif event.event_type == "TrialTerminated":
            terminals[str(event.payload["trial_id"])] = str(event.payload["status"])
    open_trials = tuple(sorted(started - set(terminals)))
    terminal_counts = tuple(sorted(Counter(terminals.values()).items()))
    base = {
        "schema_version": "research_event_replay.v1",
        "event_count": len(ordered),
        "watermark_sequence": len(ordered),
        "watermark_event_hash": ordered[-1].event_hash if ordered else None,
        "event_type_counts": sorted(event_types.items()),
        "open_trial_ids": list(open_trials),
        "terminal_status_counts": list(terminal_counts),
        "source_event_hashes": [event.event_hash for event in ordered],
    }
    return ReplayState(
        schema_version="research_event_replay.v1",
        event_count=len(ordered),
        watermark_sequence=len(ordered),
        watermark_event_hash=ordered[-1].event_hash if ordered else None,
        event_type_counts=tuple(sorted(event_types.items())),
        open_trial_ids=open_trials,
        terminal_status_counts=terminal_counts,
        projection_hash=canonical_json_hash(base),
    )


__all__ = ["build_replay_state"]
