from __future__ import annotations

from pathlib import Path

from src.alpha_foundry.dsl.identity import FactorSpecSemantics, FactorIdentityService
from src.alpha_quality.flags import ResolvedAGSFlags
from src.research_ledger.events import ResearchEventStore
from src.research_ledger.hash_utils import canonical_json_hash


def _flags() -> ResolvedAGSFlags:
    return ResolvedAGSFlags.from_settings(
        {
            "VIBE_TRADING_AGS_ENABLED": "1",
            "VIBE_TRADING_RESEARCH_EVENTS": "1",
            "VIBE_TRADING_ALPHA_FOUNDRY": "1",
            "VIBE_TRADING_FACTOR_DAG": "1",
        }
    )


def _semantics() -> FactorSpecSemantics:
    digest = canonical_json_hash({"fixture": "identity"})
    return FactorSpecSemantics(
        transform_pipeline_hash=digest,
        field_semantics={"close": "split_adjusted_eod_point_in_time"},
        signal_time="session_close_t",
        order_time="next_session_open",
        entry_price_time="next_session_open",
        execution_lag=1,
        return_horizon=5,
        universe_mask_hash=digest,
        tradability_mask_hash=digest,
    )


def _service(tmp_path: Path) -> tuple[FactorIdentityService, ResearchEventStore]:
    flags = _flags()
    store = ResearchEventStore(
        tmp_path / "research.sqlite",
        artifact_root=tmp_path / "artifacts",
        flags=flags,
        code_version="identity-test-v1",
    )
    return FactorIdentityService(store=store, flags=flags), store


def test_invalid_formula_records_failure_and_terminal_without_definition(tmp_path: Path) -> None:
    service, store = _service(tmp_path)

    result = service.record_attempt(
        trial_id="trial-invalid",
        run_id="run-1",
        candidate_id="candidate-invalid",
        formula="rank(future_return)",
        semantics=_semantics(),
    )

    assert result.status == "invalid"
    assert result.factor_spec_id is None
    assert [event.event_type for event in store.query_events()] == [
        "TrialStarted",
        "GenerationFailureRecorded",
        "TrialTerminated",
    ]
    assert store.query_events(event_type="FactorDefinitionRecorded") == []
    assert store.lifecycle_summary().open_trial_ids == ()


def test_canonical_duplicate_reuses_definition_and_records_duplicate_trial(tmp_path: Path) -> None:
    service, store = _service(tmp_path)

    first = service.record_attempt(
        trial_id="trial-first",
        run_id="run-1",
        candidate_id="candidate-first",
        formula="cs_rank(close)",
        semantics=_semantics(),
    )
    duplicate = service.record_attempt(
        trial_id="trial-duplicate",
        run_id="run-2",
        candidate_id="candidate-duplicate",
        formula="rank(close)",
        semantics=_semantics(),
    )

    definitions = store.query_events(event_type="FactorDefinitionRecorded")
    duplicate_terminal = store.query_events(
        event_type="TrialTerminated", entity_id="trial-duplicate"
    )
    assert first.status == "recorded"
    assert duplicate.status == "duplicate"
    assert first.factor_spec_id == duplicate.factor_spec_id
    assert len(definitions) == 1
    assert definitions[0].payload["metadata"]["originating_trial_id"] == "trial-first"
    assert duplicate_terminal[0].payload["status"] == "duplicate"
    assert duplicate_terminal[0].payload["reason_codes"] == ("CANONICAL_DUPLICATE",)
    assert store.lifecycle_summary().open_trial_ids == ("trial-first",)


def test_definition_recording_retry_is_idempotent_not_a_duplicate(tmp_path: Path) -> None:
    service, store = _service(tmp_path)
    kwargs = {
        "trial_id": "trial-retry",
        "run_id": "run-1",
        "candidate_id": "candidate-retry",
        "formula": "rank(close)",
        "semantics": _semantics(),
    }

    first = service.record_attempt(**kwargs)
    retried = service.record_attempt(**kwargs)

    assert first == retried
    assert len(store.query_events(event_type="TrialStarted")) == 1
    assert len(store.query_events(event_type="FactorDefinitionRecorded")) == 1
    assert store.query_events(event_type="TrialTerminated") == []
