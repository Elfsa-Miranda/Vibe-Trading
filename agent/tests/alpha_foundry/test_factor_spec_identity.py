from __future__ import annotations

import pytest

from src.alpha_foundry.candidate_pool import candidate_matches_id, make_candidate
from src.alpha_foundry.dsl.identity import (
    FactorSpecSemantics,
    build_factor_spec_identity,
)
from src.alpha_quality.flags import ResolvedAGSFlags
from src.research_ledger.hash_utils import canonical_json_hash


def _hash(name: str) -> str:
    return canonical_json_hash({"name": name})


def _semantics(**overrides: object) -> FactorSpecSemantics:
    values: dict[str, object] = {
        "transform_pipeline_hash": _hash("transform-v1"),
        "field_semantics": {
            "close": "split_adjusted_eod_point_in_time",
            "volume": "exchange_reported_eod",
        },
        "signal_time": "session_close_t",
        "order_time": "next_session_open",
        "entry_price_time": "next_session_open",
        "execution_lag": 1,
        "return_horizon": 5,
        "universe_mask_hash": _hash("universe"),
        "tradability_mask_hash": _hash("tradability"),
    }
    values.update(overrides)
    return FactorSpecSemantics(**values)  # type: ignore[arg-type]


def _canonical_flags() -> ResolvedAGSFlags:
    return ResolvedAGSFlags.from_settings(
        {
            "VIBE_TRADING_AGS_ENABLED": "1",
            "VIBE_TRADING_FACTOR_DAG": "1",
        }
    )


def test_transform_or_timing_change_preserves_expression_but_changes_factor_spec() -> None:
    original = build_factor_spec_identity("rank(close)", _semantics())
    transform_changed = build_factor_spec_identity(
        "rank(close)", _semantics(transform_pipeline_hash=_hash("transform-v2"))
    )
    timing_changed = build_factor_spec_identity(
        "rank(close)", _semantics(execution_lag=2, order_time="session_open_plus_one")
    )

    assert original.expression.expression_id == transform_changed.expression.expression_id
    assert original.expression.expression_id == timing_changed.expression.expression_id
    assert original.factor_spec_id != transform_changed.factor_spec_id
    assert original.factor_spec_id != timing_changed.factor_spec_id


def test_field_and_mask_semantics_are_value_identity_not_metadata() -> None:
    original = build_factor_spec_identity("rank(close)", _semantics())
    field_changed = build_factor_spec_identity(
        "rank(close)",
        _semantics(field_semantics={"close": "unadjusted_eod_point_in_time"}),
    )
    mask_changed = build_factor_spec_identity(
        "rank(close)", _semantics(tradability_mask_hash=_hash("tradability-v2"))
    )

    assert original.factor_spec_id != field_changed.factor_spec_id
    assert original.factor_spec_id != mask_changed.factor_spec_id


def test_invalid_semantics_fail_closed() -> None:
    with pytest.raises(ValueError, match="execution_lag"):
        _semantics(execution_lag=0)
    with pytest.raises(ValueError, match="content hash"):
        _semantics(transform_pipeline_hash="caller-score")
    with pytest.raises(ValueError, match="missing expression fields"):
        build_factor_spec_identity(
            "rank(close)", _semantics(field_semantics={"volume": "exchange_reported_eod"})
        )


def test_feature_off_candidate_identity_matches_legacy_raw_formula_golden() -> None:
    candidate = make_candidate("seed-1", "rank(close)", mutation="identity")

    assert candidate.formula_hash == canonical_json_hash({"formula": "rank(close)"})
    assert candidate.candidate_id == candidate.formula_hash.removeprefix("sha256:")[:16]
    assert candidate.expression_id is None
    assert candidate.factor_spec_id is None


def test_canonical_candidate_mode_uses_factor_spec_and_preserves_legacy_alias() -> None:
    left = make_candidate(
        "seed-1",
        " cs_rank( close ) ",
        mutation="identity",
        flags=_canonical_flags(),
        factor_semantics=_semantics(),
    )
    right = make_candidate(
        "seed-1",
        "rank(close)",
        mutation="identity",
        flags=_canonical_flags(),
        factor_semantics=_semantics(),
    )

    assert left.formula_hash != right.formula_hash
    assert left.expression_id == right.expression_id
    assert left.factor_spec_id == right.factor_spec_id
    assert left.candidate_id == right.candidate_id
    assert left.metadata["legacy_formula_hash"] == left.formula_hash


def test_canonical_candidate_mode_requires_complete_semantics() -> None:
    with pytest.raises(ValueError, match="factor_semantics"):
        make_candidate(
            "seed-1",
            "rank(close)",
            mutation="identity",
            flags=_canonical_flags(),
        )


def test_canonical_candidate_preserves_resolvable_v31_raw_identifier_alias() -> None:
    candidate = make_candidate(
        "seed-1", "rank(close)", mutation="identity", flags=_canonical_flags(), factor_semantics=_semantics()
    )
    legacy_id = candidate.formula_hash.removeprefix("sha256:")[:16]

    assert candidate_matches_id(candidate, candidate.candidate_id)
    assert candidate_matches_id(candidate, legacy_id)
