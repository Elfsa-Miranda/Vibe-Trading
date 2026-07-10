import pytest

from src.alpha_quality.falsification import FalsificationContract, FalsificationService
from src.alpha_quality.falsification.executor import FixedHorizonExecutor, FixedTestEvidence, classify, execute_fixed_family
from src.alpha_quality.falsification.policy import (
    APPROVED_SEQUENTIAL_METHOD,
    sequential_method_availability,
)
from src.alpha_quality.flags import ResolvedAGSFlags
from src.research_ledger.events import ResearchEventStore
from src.research_ledger.hash_utils import canonical_json_hash


def test_underpowered_decisive_result_is_inconclusive_not_falsified() -> None:
    result = classify(support_p=.001, contradiction_p=.001, lower_p=None, upper_p=None, alpha=.05, effective_n=2, min_effective_n=10, negative_control_available=True)
    assert result.outcome == "inconclusive" and result.cap == "RESEARCH_ONLY"


def test_unavailable_negative_control_does_not_silently_pass() -> None:
    result = classify(support_p=.001, contradiction_p=None, lower_p=None, upper_p=None, alpha=.05, effective_n=10, min_effective_n=10, negative_control_available=False)
    assert result.outcome == "inconclusive" and result.cap == "RESEARCH_ONLY"


def test_unapproved_sequential_method_is_typed_unavailable_without_fallback() -> None:
    approved = sequential_method_availability(APPROVED_SEQUENTIAL_METHOD)
    repeated_p = sequential_method_availability("ordinary_repeated_p_values")

    assert approved.status == "approved"
    assert repeated_p.status == "unavailable"
    assert repeated_p.reason_code == "SEQUENTIAL_METHOD_NOT_APPROVED"


def test_decisive_directional_contradiction_is_falsified() -> None:
    result = execute_fixed_family([FixedTestEvidence("direction", "positive", True, 100, 20, .001, -.2)], alpha=.05)
    assert result.outcome == "falsified"
    assert result.failure_codes == ("DECISIVE_MECHANISM_CONTRADICTION",)


def test_advisory_support_cannot_replace_missing_decisive_evidence() -> None:
    tests = [
        FixedTestEvidence("decisive", "positive", True, 0, 20, available=False, unavailability_code="TEST_UNAVAILABLE"),
        FixedTestEvidence("advisory", "positive", False, 100, 20, .001, .2),
    ]
    result = execute_fixed_family(tests, alpha=.05)
    assert result.outcome == "inconclusive" and result.cap == "RESEARCH_ONLY"


def test_statistical_significance_without_sesoi_is_inconclusive() -> None:
    result = execute_fixed_family(
        [FixedTestEvidence("direction", "positive", True, 100, 20, .001, .01, minimum_effect=.05)],
        alpha=.05,
    )
    assert result.outcome == "inconclusive"
    assert "SESOI_NOT_MET" in result.warnings


def test_fixed_result_is_content_addressed_and_append_only(tmp_path) -> None:
    flags = ResolvedAGSFlags.from_settings({"VIBE_TRADING_AGS_ENABLED": "1", "VIBE_TRADING_RESEARCH_EVENTS": "1", "VIBE_TRADING_FALSIFICATION_CONTRACT": "1"})
    store = ResearchEventStore(tmp_path / "research.sqlite", artifact_root=tmp_path / "artifacts", flags=flags, code_version="fixed-test-v1")
    service = FalsificationService(store=store, flags=flags)
    digest = canonical_json_hash({"fixture": "fixed"})
    contract = FalsificationContract("factor-1", digest, "validation_ic", "positive", .01, "ic", "date", digest, digest, "family-1", .05, "hac", 1, "fixed", True, digest)
    service.register(contract, run_id="run-1")
    result = execute_fixed_family([FixedTestEvidence("direction", "positive", True, 100, 20, .001, .2)], alpha=.05)
    first = service.record_fixed_result(contract, result, run_id="run-1")
    retried = service.record_fixed_result(contract, result, run_id="run-1")

    assert first.event_hash == retried.event_hash
    assert first.payload["outcome"] == "supported"
    assert len(store.query_events(event_type="FalsificationResultRecorded")) == 1
    accesses = store.query_events(event_type="OutcomeDataAccessed")
    assert len(accesses) == 1
    assert accesses[0].payload["data_scope"] == "valid"
    assert store.verify_chain()


def test_fixed_service_rejects_sequential_contract_and_non_validation_access(tmp_path) -> None:
    flags = ResolvedAGSFlags.from_settings({"VIBE_TRADING_AGS_ENABLED": "1", "VIBE_TRADING_RESEARCH_EVENTS": "1", "VIBE_TRADING_FALSIFICATION_CONTRACT": "1"})
    store = ResearchEventStore(tmp_path / "research.sqlite", artifact_root=tmp_path / "artifacts", flags=flags, code_version="fixed-test-v1")
    service = FalsificationService(store=store, flags=flags)
    digest = canonical_json_hash({"fixture": "fixed-boundary"})
    sequential_contract = FalsificationContract("factor-1", digest, "validation_ic", "positive", .01, "ic", "date", digest, digest, "family-1", .05, "hac", 3, "e_process_boundary_or_max_looks.v1", True, digest)
    service.register(sequential_contract, run_id="run-1")
    result = execute_fixed_family([FixedTestEvidence("direction", "positive", True, 100, 20, .001, .2)], alpha=.05)

    with pytest.raises(ValueError, match="fixed result service"):
        service.record_fixed_result(sequential_contract, result, run_id="run-1")
    for forbidden_scope in ("test", "final_test", "forward"):
        with pytest.raises(ValueError, match="validation-only"):
            service.outcome_access(sequential_contract, data_scope=forbidden_scope)  # type: ignore[arg-type]

    assert store.query_events(event_type="OutcomeDataAccessed") == []


def test_fixed_executor_service_is_feature_gated(tmp_path) -> None:
    flags = ResolvedAGSFlags.from_settings({"VIBE_TRADING_AGS_ENABLED": "1", "VIBE_TRADING_RESEARCH_EVENTS": "1"})
    store = ResearchEventStore(tmp_path / "db.sqlite", artifact_root=tmp_path / "artifacts", flags=flags, code_version="test")
    with pytest.raises(RuntimeError, match="disabled"):
        FalsificationService(store=store, flags=flags)
    with pytest.raises(RuntimeError, match="disabled"):
        FixedHorizonExecutor(flags=flags)
