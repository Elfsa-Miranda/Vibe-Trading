from __future__ import annotations

import pytest

from src.alpha_quality.falsification.mei import (
    MECHANISM_EVIDENCE_SCHEMA_VERSION,
    MECHANISM_EVIDENCE_TRUTH_TABLE_VERSION,
    MechanismEvidenceRef,
    aggregate_mechanism_evidence,
)
from src.research_ledger.hash_utils import canonical_json_hash


FACTOR_ID = "factor-spec-1"
POLICY_VERSION = "mechanism-policy.v1"
POLICY_HASH = canonical_json_hash({"policy": POLICY_VERSION})


def _evidence(
    name: str,
    outcome: str,
    *,
    decisive: bool = True,
    factor_spec_id: str = FACTOR_ID,
    policy_version: str = POLICY_VERSION,
    policy_hash: str = POLICY_HASH,
    reason_codes: tuple[str, ...] = (),
    warning_codes: tuple[str, ...] = (),
    limitation_codes: tuple[str, ...] = (),
) -> MechanismEvidenceRef:
    return MechanismEvidenceRef(
        factor_spec_id=factor_spec_id,
        result_hash=canonical_json_hash({"result": name}),
        event_hash=canonical_json_hash({"event": name}),
        policy_version=policy_version,
        policy_hash=policy_hash,
        outcome=outcome,  # type: ignore[arg-type]
        decisive=decisive,
        reason_codes=reason_codes,
        warning_codes=warning_codes,
        limitation_codes=limitation_codes,
    )


def _aggregate(*items: MechanismEvidenceRef):
    return aggregate_mechanism_evidence(
        items,
        factor_spec_id=FACTOR_ID,
        policy_version=POLICY_VERSION,
        policy_hash=POLICY_HASH,
    )


def _assert_no_forbidden_key(value: object) -> None:
    forbidden = (
        "probability",
        "probabilities",
        "calibrated_probability",
        "support_probability",
        "confidence",
        "confidence_score",
        "posterior",
        "likelihood",
        "score",
        "rank",
    )
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = str(key).lower()
            assert all(term not in normalized for term in forbidden)
            _assert_no_forbidden_key(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_forbidden_key(nested)


def test_mechanism_evidence_v1_never_emits_probability() -> None:
    result = _aggregate(
        _evidence(
            "decisive",
            "supported",
            reason_codes=("DIRECTION_SUPPORTED",),
            warning_codes=("BOUNDED_EVIDENCE_ONLY",),
            limitation_codes=("VALID_SCOPE_ONLY",),
        )
    )

    payload = result.to_dict()
    assert payload["schema_version"] == MECHANISM_EVIDENCE_SCHEMA_VERSION
    assert payload["ordinal_state"] == "supported"
    _assert_no_forbidden_key(payload)


def test_decisive_contradiction_maps_to_falsified() -> None:
    result = _aggregate(
        _evidence("advisory-support", "supported", decisive=False),
        _evidence("decisive-contradiction", "contradiction"),
    )

    assert result.ordinal_state == "falsified"
    assert "DECISIVE_MECHANISM_CONTRADICTION" in result.reason_codes


@pytest.mark.parametrize(
    ("outcome", "reason"),
    [
        ("missing", "DECISIVE_EVIDENCE_MISSING"),
        ("unavailable", "DECISIVE_TEST_UNAVAILABLE"),
        ("low_power", "DECISIVE_TEST_LOW_POWER"),
        ("inconclusive", "DECISIVE_TEST_INCONCLUSIVE"),
    ],
)
def test_missing_or_low_power_decisive_test_maps_to_inconclusive(
    outcome: str, reason: str
) -> None:
    result = _aggregate(
        _evidence("decisive-gap", outcome),
        _evidence("advisory-support", "supported", decisive=False),
    )

    assert result.ordinal_state == "inconclusive"
    assert reason in result.reason_codes


def test_partial_and_full_support_truth_table_is_versioned() -> None:
    full = _aggregate(
        _evidence("decisive", "supported"),
        _evidence("advisory", "supported", decisive=False),
    )
    partial = _aggregate(
        _evidence("decisive", "supported"),
        _evidence("advisory", "inconclusive", decisive=False),
    )
    advisory_only = _aggregate(_evidence("advisory", "supported", decisive=False))

    assert full.ordinal_state == "supported"
    assert partial.ordinal_state == "partial_support"
    assert advisory_only.ordinal_state == "inconclusive"
    assert full.truth_table_version == MECHANISM_EVIDENCE_TRUTH_TABLE_VERSION
    assert partial.truth_table_version == MECHANISM_EVIDENCE_TRUTH_TABLE_VERSION


def test_mei_is_order_independent_and_content_addressed() -> None:
    decisive = _evidence("decisive", "supported", reason_codes=("B", "A", "A"))
    advisory = _evidence("advisory", "supported", decisive=False)

    first = _aggregate(decisive, advisory)
    second = _aggregate(advisory, decisive)

    assert first == second
    assert first.mei_hash == second.mei_hash
    assert first.source_result_hashes == tuple(sorted(first.source_result_hashes))
    assert first.source_event_hashes == tuple(sorted(first.source_event_hashes))
    assert first.reason_codes == tuple(sorted(set(first.reason_codes)))


def test_identical_duplicate_hash_is_deduplicated_but_conflict_is_rejected() -> None:
    item = _evidence("same", "supported")
    deduplicated = _aggregate(item, item)
    assert deduplicated.source_result_hashes == (item.result_hash,)

    conflict = MechanismEvidenceRef(
        factor_spec_id=item.factor_spec_id,
        result_hash=item.result_hash,
        event_hash=item.event_hash,
        policy_version=item.policy_version,
        policy_hash=item.policy_hash,
        outcome="contradiction",
        decisive=True,
    )
    with pytest.raises(ValueError, match="conflicting evidence"):
        _aggregate(item, conflict)


def test_factor_and_policy_mismatch_are_rejected() -> None:
    with pytest.raises(ValueError, match="factor mismatch"):
        _aggregate(_evidence("wrong-factor", "supported", factor_spec_id="factor-spec-2"))

    with pytest.raises(ValueError, match="policy mismatch"):
        _aggregate(
            _evidence(
                "wrong-policy",
                "supported",
                policy_version="mechanism-policy.v2",
                policy_hash=canonical_json_hash({"policy": "mechanism-policy.v2"}),
            )
        )


def test_mei_rejects_forged_hashes_and_mutable_code_strings() -> None:
    with pytest.raises(ValueError, match="canonical sha256"):
        MechanismEvidenceRef(
            factor_spec_id=FACTOR_ID,
            result_hash="not-a-hash",
            event_hash=canonical_json_hash({"event": "x"}),
            policy_version=POLICY_VERSION,
            policy_hash=POLICY_HASH,
            outcome="supported",
            decisive=True,
        )
    with pytest.raises(ValueError, match="sequence of codes"):
        _evidence("bad-codes", "supported", reason_codes="NOT_A_SEQUENCE")  # type: ignore[arg-type]
