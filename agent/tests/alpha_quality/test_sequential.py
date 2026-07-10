from __future__ import annotations

import random
from dataclasses import FrozenInstanceError, replace

import pytest
from scipy.stats import beta

from src.alpha_quality.falsification.sequential import (
    APPROVED_METHOD,
    APPROVED_STOPPING_RULE,
    SequentialBlock,
    SequentialExecutor,
    SequentialProtocol,
    UnsupportedSequentialMethod,
)
from src.alpha_quality.flags import ResolvedAGSFlags
from src.research_ledger.hash_utils import canonical_json_hash


def _digest(label: object) -> str:
    return canonical_json_hash({"fixture": label})


def _flags(*, enabled: bool = True) -> ResolvedAGSFlags:
    settings = {
        "VIBE_TRADING_AGS_ENABLED": "1" if enabled else "0",
        "VIBE_TRADING_FALSIFICATION_CONTRACT": "1",
    }
    return ResolvedAGSFlags.from_settings(settings)


def _protocol(*, maximum_looks: int = 3, **changes: object) -> SequentialProtocol:
    values: dict[str, object] = {
        "factor_spec_id": "factor-1",
        "snapshot_hash": _digest("snapshot"),
        "manifest_hash": _digest("manifest"),
        "filtration_hash": _digest("filtration"),
        "policy_hash": _digest("policy"),
        "block_schedule": tuple(f"block-{index}" for index in range(maximum_looks)),
        "maximum_looks": maximum_looks,
        "expected_direction": "positive",
        "lower_bound": -1.0,
        "upper_bound": 1.0,
        "sesoi": 0.0,
    }
    values.update(changes)
    return SequentialProtocol(**values)  # type: ignore[arg-type]


def _block(
    protocol: SequentialProtocol,
    index: int,
    values: tuple[float, ...] = (0.0,),
    *,
    information_time: int | None = None,
    unit_label: str | None = None,
) -> SequentialBlock:
    prefix = unit_label or f"look-{index}"
    return SequentialBlock(
        block_id=protocol.block_schedule[index],
        information_time=index + 1 if information_time is None else information_time,
        snapshot_hash=protocol.snapshot_hash,
        manifest_hash=protocol.manifest_hash,
        filtration_hash=protocol.filtration_hash,
        scope="valid",
        observations=tuple((_digest((prefix, position)), value) for position, value in enumerate(values)),
    )


def test_sequential_mode_rejects_ordinary_repeated_p_values() -> None:
    protocol = _protocol()
    executor = SequentialExecutor(flags=_flags())
    state = executor.initial_state(protocol)

    with pytest.raises(ValueError, match="p/e-values"):
        executor.advance(protocol, state, _block(protocol, 0), p_value=0.049)
    with pytest.raises(ValueError, match="p/e-values"):
        executor.advance(protocol, state, _block(protocol, 0), e_value=50.0)
    with pytest.raises(UnsupportedSequentialMethod):
        _protocol(method="ordinary_repeated_p_values")


def test_sequential_look_cannot_reuse_observed_block() -> None:
    protocol = _protocol()
    executor = SequentialExecutor(flags=_flags())
    first = _block(protocol, 0, (0.2, -0.1), information_time=2)
    state, _ = executor.advance(protocol, executor.initial_state(protocol), first)

    with pytest.raises(ValueError, match="reuse an observed block"):
        executor.advance(protocol, state, first)

    reused_unit = SequentialBlock(
        block_id=protocol.block_schedule[1],
        information_time=3,
        snapshot_hash=protocol.snapshot_hash,
        manifest_hash=protocol.manifest_hash,
        filtration_hash=protocol.filtration_hash,
        scope="valid",
        observations=((first.unit_hashes[0], 0.1),),
    )
    with pytest.raises(ValueError, match="reuse an observed unit"):
        executor.advance(protocol, state, reused_unit)


def test_stopping_rule_and_max_looks_are_frozen() -> None:
    protocol = _protocol(maximum_looks=2)
    executor = SequentialExecutor(flags=_flags())
    state = executor.initial_state(protocol)

    with pytest.raises(FrozenInstanceError):
        protocol.maximum_looks = 3  # type: ignore[misc]
    with pytest.raises(UnsupportedSequentialMethod):
        _protocol(stopping_rule="caller_decides_after_each_look")

    changed = _protocol(maximum_looks=3)
    with pytest.raises(ValueError, match="different frozen"):
        executor.advance(changed, state, _block(changed, 0))

    state, first = executor.advance(protocol, state, _block(protocol, 0))
    assert first.status == "continue" and first.stop_reason == "NONE"
    state, second = executor.advance(protocol, state, _block(protocol, 1))
    assert state.stopped
    assert second.status == "max_looks_reached" and second.stop_reason == "MAX_LOOKS"
    with pytest.raises(ValueError, match="after the frozen stopping rule"):
        executor.advance(protocol, state, _block(protocol, 1, unit_label="new"))


def test_null_simulation_preserves_nominal_error_for_approved_e_process() -> None:
    """A fixed seed suite checks an exact one-sided binomial confidence bound."""

    looks = 40
    trials_per_seed = 64
    seeds = (113, 271, 811, 1597)
    protocol = _protocol(
        maximum_looks=looks,
        family_alpha=0.10,
        support_alpha=0.05,
        contradiction_alpha=0.05,
    )
    executor = SequentialExecutor(flags=_flags())
    support_crossings = 0
    total_trials = 0
    for seed in seeds:
        rng = random.Random(seed)
        for trial in range(trials_per_seed):
            state = executor.initial_state(protocol)
            for look_index in range(looks):
                observation = 1.0 if rng.getrandbits(1) else -1.0
                block = _block(
                    protocol,
                    look_index,
                    (observation,),
                    unit_label=f"seed-{seed}-trial-{trial}-look-{look_index}",
                )
                state, look = executor.advance(protocol, state, block)
                if look.status == "support_boundary_crossed":
                    support_crossings += 1
                    break
                if state.stopped:
                    break
            total_trials += 1

    # Clopper-Pearson's one-sided 99% upper confidence limit.  This reports
    # uncertainty rather than accepting a lucky point estimate.  A repeated
    # 0.05 p-value rule would cross in about 87% of 40 looks and fail loudly.
    upper = 1.0 if support_crossings == total_trials else float(
        beta.ppf(0.99, support_crossings + 1, total_trials - support_crossings)
    )
    assert upper <= protocol.support_alpha, {
        "crossings": support_crossings,
        "trials": total_trials,
        "cp_upper_99": upper,
    }


def test_protocol_is_validation_only_and_raw_blocks_are_bounded() -> None:
    with pytest.raises(ValueError, match="validation-only"):
        _protocol(scope="test")
    protocol = _protocol()
    executor = SequentialExecutor(flags=_flags())
    state = executor.initial_state(protocol)
    with pytest.raises(ValueError, match="outside the frozen bounds"):
        executor.advance(protocol, state, _block(protocol, 0, (1.0001,)))
    with pytest.raises(ValueError, match="finite"):
        _block(protocol, 0, (float("nan"),))


def test_predeclared_schedule_information_time_and_context_are_enforced() -> None:
    protocol = _protocol(maximum_looks=3)
    executor = SequentialExecutor(flags=_flags())
    state, _ = executor.advance(protocol, executor.initial_state(protocol), _block(protocol, 0))

    out_of_order = replace(_block(protocol, 1), block_id=protocol.block_schedule[2])
    with pytest.raises(ValueError, match="next pre-registered"):
        executor.advance(protocol, state, out_of_order)
    with pytest.raises(ValueError, match="cumulative unobserved"):
        executor.advance(protocol, state, _block(protocol, 1, information_time=1))
    wrong_snapshot = replace(_block(protocol, 1), snapshot_hash=_digest("other-snapshot"))
    with pytest.raises(ValueError, match="snapshot or manifest"):
        executor.advance(protocol, state, wrong_snapshot)


def test_component_log_state_and_replay_are_deterministic() -> None:
    protocol = _protocol(maximum_looks=3)
    executor = SequentialExecutor(flags=_flags())
    blocks = (
        _block(protocol, 0, (0.5, 0.25), information_time=2),
        _block(protocol, 1, (-0.25, 0.75), information_time=4),
        _block(protocol, 2, (0.1, -0.1), information_time=6),
    )
    state, looks = executor.replay(protocol, blocks)
    replayed_state, replayed_looks = executor.replay(protocol, blocks, expected_looks=looks)

    assert state.state_hash == replayed_state.state_hash
    assert tuple(look.look_hash for look in looks) == tuple(look.look_hash for look in replayed_looks)
    assert len(looks[-1].support_component_log_capitals) == len(protocol.lambda_grid)
    assert looks[-1].support_log_evidence == state.support_log_evidence
    assert looks[-1].status == "max_looks_reached"


def test_caller_cannot_forge_continuation_state_or_cumulative_evidence() -> None:
    protocol = _protocol(maximum_looks=3)
    executor = SequentialExecutor(flags=_flags())
    state, _ = executor.advance(
        protocol,
        executor.initial_state(protocol),
        _block(protocol, 0),
    )
    forged = replace(
        state,
        support_log_evidence=state.support_log_evidence + 0.5,
    )

    with pytest.raises(ValueError, match="internally inconsistent"):
        executor.advance(protocol, forged, _block(protocol, 1))


def test_sequential_executor_is_feature_gated_without_work() -> None:
    with pytest.raises(RuntimeError, match="disabled"):
        SequentialExecutor(flags=_flags(enabled=False))


def test_approved_protocol_literals_are_stable() -> None:
    protocol = _protocol()
    assert protocol.method == APPROVED_METHOD == "bounded_mean_mixture_e.v1"
    assert protocol.stopping_rule == APPROVED_STOPPING_RULE == "e_process_boundary_or_max_looks.v1"
    assert protocol.protocol_hash == protocol.contract_hash
