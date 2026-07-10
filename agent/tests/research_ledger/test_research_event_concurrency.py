from __future__ import annotations

import multiprocessing
from pathlib import Path

from src.alpha_quality.flags import ResolvedAGSFlags
from src.research_ledger.events import EventDraft, ResearchEventStore


def _append_batch(args: tuple[str, str, int, int]) -> int:
    db_path, artifact_root, worker_id, count = args
    flags = ResolvedAGSFlags.from_settings(
        {
            "VIBE_TRADING_AGS_ENABLED": "1",
            "VIBE_TRADING_RESEARCH_EVENTS": "1",
        }
    )
    store = ResearchEventStore(
        db_path,
        artifact_root=artifact_root,
        flags=flags,
        code_version="spawn-concurrency-v1",
        busy_timeout_ms=30_000,
        max_retries=24,
    )
    for index in range(count):
        identity = f"factor-{worker_id}-{index}"
        store.append_event(
            EventDraft(
                event_type="FactorDefinitionRecorded",
                entity_id=identity,
                run_id=f"run-{worker_id}",
                payload_schema_version="factor_definition_recorded.v1",
                payload={
                    "factor_spec_id": identity,
                    "expression_id": f"expression-{worker_id}-{index}",
                    "canonical_ast_hash": "sha256:" + f"{worker_id:02x}{index:04x}".ljust(64, "a"),
                    "grammar_version": "1.0.0",
                    "grammar_hash": "sha256:" + "b" * 64,
                    "metadata": {},
                    "artifact_refs": [],
                },
                idempotency_key=f"factor-definition:{worker_id}:{index}",
            )
        )
    return count


def test_spawn_process_concurrent_appends_preserve_count_and_chain(tmp_path: Path) -> None:
    db_path = tmp_path / "research.sqlite"
    artifact_root = tmp_path / "artifacts"
    context = multiprocessing.get_context("spawn")
    batches = [(str(db_path), str(artifact_root), worker, 50) for worker in range(8)]

    with context.Pool(processes=8) as pool:
        counts = pool.map(_append_batch, batches)

    flags = ResolvedAGSFlags.from_settings(
        {
            "VIBE_TRADING_AGS_ENABLED": "1",
            "VIBE_TRADING_RESEARCH_EVENTS": "1",
        }
    )
    store = ResearchEventStore(
        db_path,
        artifact_root=artifact_root,
        flags=flags,
        code_version="spawn-concurrency-v1",
    )
    events = store.query_events()

    assert counts == [50] * 8
    assert len(events) == 400
    assert len({event.event_id for event in events}) == 400
    assert len({event.idempotency_key for event in events}) == 400
    assert store.verify_chain()
