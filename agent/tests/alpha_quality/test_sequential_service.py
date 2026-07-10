from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from src.alpha_quality.falsification import FalsificationContract
from src.alpha_quality.falsification.executor import FixedTestEvidence, execute_fixed_family
from src.alpha_quality.falsification.sequential import (
    APPROVED_STOPPING_RULE,
    SequentialBlock,
    SequentialExecutor,
    SequentialProtocol,
)
from src.alpha_quality.falsification.sequential_service import (
    SequentialFalsificationService,
)
from src.alpha_quality.falsification.service import FalsificationService
from src.alpha_quality.flags import ResolvedAGSFlags
from src.research_ledger.events import ResearchEventStore
from src.research_ledger.hash_utils import canonical_json_hash


def _digest(name: str) -> str:
    return canonical_json_hash({"fixture": name})


def _flags(*, falsification: bool = True) -> ResolvedAGSFlags:
    return ResolvedAGSFlags.from_settings(
        {
            "VIBE_TRADING_AGS_ENABLED": "1",
            "VIBE_TRADING_RESEARCH_EVENTS": "1",
            "VIBE_TRADING_FALSIFICATION_CONTRACT": "1" if falsification else "0",
        }
    )


def _store(tmp_path: Path, flags: ResolvedAGSFlags) -> ResearchEventStore:
    return ResearchEventStore(
        tmp_path / "research.sqlite",
        artifact_root=tmp_path / "artifacts",
        flags=flags,
        code_version="p8-service-test",
    )


def _sequential_pair() -> tuple[FalsificationContract, SequentialProtocol]:
    policy_hash = _digest("policy")
    protocol = SequentialProtocol(
        factor_spec_id="factor-sequential",
        snapshot_hash=_digest("snapshot"),
        manifest_hash=_digest("manifest"),
        filtration_hash=_digest("filtration"),
        policy_hash=policy_hash,
        block_schedule=("block-1", "block-2"),
        maximum_looks=2,
        expected_direction="positive",
        lower_bound=-1.0,
        upper_bound=1.0,
        sesoi=0.1,
    )
    contract = FalsificationContract(
        factor_spec_id=protocol.factor_spec_id,
        capability_hash=_digest("capability"),
        estimand="bounded_validation_mean",
        direction=protocol.expected_direction,
        sesoi=protocol.sesoi,
        units="normalized_effect",
        sample_unit="validation_observation",
        conditioning_hash=_digest("conditioning"),
        regime_hash=_digest("regime"),
        family_id="sequential-family",
        alpha=protocol.family_alpha,
        dependence_method="predictable_blocks",
        maximum_looks=protocol.maximum_looks,
        stopping_rule=APPROVED_STOPPING_RULE,
        decisive=True,
        policy_hash=policy_hash,
    )
    return contract, protocol


def _block(protocol: SequentialProtocol, block_id: str, start: int, values: tuple[float, ...]):
    return SequentialBlock(
        block_id=block_id,
        information_time=start + len(values),
        snapshot_hash=protocol.snapshot_hash,
        manifest_hash=protocol.manifest_hash,
        filtration_hash=protocol.filtration_hash,
        scope="valid",
        observations=tuple(
            (_digest(f"unit-{start + offset}"), value)
            for offset, value in enumerate(values)
        ),
    )


def test_sequential_protocol_looks_result_and_mei_are_append_only_and_replayable(
    tmp_path: Path,
) -> None:
    flags = _flags()
    store = _store(tmp_path, flags)
    service = SequentialFalsificationService(store=store, flags=flags)
    contract, protocol = _sequential_pair()

    registration = service.register_protocol(contract, protocol, run_id="run-p8")
    first_block = _block(protocol, "block-1", 0, (0.0, 0.1))
    first_event = service.record_block(contract, protocol, first_block, run_id="run-p8")
    second_block = _block(protocol, "block-2", 2, (0.0,))
    second_event = service.record_block(contract, protocol, second_block, run_id="run-p8")
    result_event = service.record_terminal_result(contract, protocol, run_id="run-p8")
    index = service.aggregate_results(
        ((contract, result_event),),
        factor_spec_id=contract.factor_spec_id,
        policy_version="mechanism-policy.v1",
        policy_hash=contract.policy_hash,
    )
    mei_event = service.record_mechanism_index(index, run_id="run-p8")

    assert registration.payload["maximum_looks"] == 2
    assert first_event.payload["look_index"] == 1
    assert second_event.payload["previous_look_event_hash"] == first_event.event_hash
    assert second_event.payload["status"] == "max_looks_reached"
    assert result_event.payload["outcome"] == "inconclusive"
    assert mei_event.payload["ordinal_state"] == "inconclusive"
    assert store.verify_chain()
    assert store.replay().event_count == 7


def test_sequential_service_recomputes_and_rejects_caller_forged_evidence(
    tmp_path: Path,
) -> None:
    flags = _flags()
    store = _store(tmp_path, flags)
    service = SequentialFalsificationService(store=store, flags=flags)
    executor = SequentialExecutor(flags=flags)
    contract, protocol = _sequential_pair()
    service.register_protocol(contract, protocol, run_id="run-p8")
    block = _block(protocol, "block-1", 0, (0.0, 0.1))
    _, look = executor.advance(protocol, executor.initial_state(protocol), block)
    forged = replace(look, support_log_evidence=look.support_log_evidence + 0.5)

    with pytest.raises(ValueError, match="differs from deterministic"):
        service.record_look(contract, protocol, block, forged, run_id="run-p8")

    assert store.query_events(event_type="SequentialLookRecorded") == []


def test_fixed_v2_result_provenance_builds_mei_without_caller_role_override(
    tmp_path: Path,
) -> None:
    flags = _flags()
    store = _store(tmp_path, flags)
    fixed_service = FalsificationService(store=store, flags=flags)
    mei_service = SequentialFalsificationService(store=store, flags=flags)
    digest = _digest("fixed")
    contract = FalsificationContract(
        "factor-fixed", digest, "validation_mean", "positive", 0.01,
        "effect", "date", digest, digest, "family", 0.05, "hac", 1,
        "fixed", True, _digest("fixed-policy"),
    )
    fixed_service.register(contract, run_id="run-fixed")
    result = execute_fixed_family(
        [FixedTestEvidence("direction", "positive", True, 100, 20, 0.001, 0.2)],
        alpha=contract.alpha,
    )
    result_event = fixed_service.record_fixed_result(contract, result, run_id="run-fixed")

    index = mei_service.aggregate_results(
        ((contract, result_event),),
        factor_spec_id=contract.factor_spec_id,
        policy_version="mechanism-policy.v1",
        policy_hash=contract.policy_hash,
    )
    persisted = mei_service.record_mechanism_index(index, run_id="run-fixed")

    assert index.ordinal_state == "supported"
    assert persisted.payload["decisive_event_hashes"] == (result_event.event_hash,)
    assert store.verify_chain()


def test_sequential_service_feature_off_refuses_before_any_event_write(tmp_path: Path) -> None:
    flags = _flags(falsification=False)
    store = _store(tmp_path, flags)

    with pytest.raises(RuntimeError, match="disabled"):
        SequentialFalsificationService(store=store, flags=flags)

    assert store.query_events() == []
