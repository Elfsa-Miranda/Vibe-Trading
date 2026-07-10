from __future__ import annotations

import pytest

from src.alpha_foundry.dag import FactorDAGError, FactorDAGProjector, FactorDAGService
from src.alpha_foundry.dag.bootstrap import build_registry_bootstrap_payload
from src.alpha_foundry.dag.model import DerivationEdge, FactorNode
from src.alpha_foundry.dag.projector import _depths
from src.alpha_foundry.dsl.identity import FactorIdentityService
from src.alpha_foundry.dsl.grammar import DEFAULT_GRAMMAR
from src.alpha_foundry.dsl.identity import build_expression_identity
from src.research_ledger.events import (
    EventDraft, EventValidationError, ResearchEventEnvelope,
)
from src.research_ledger.hash_utils import canonical_json_hash

from test_factor_dag import _definition, _flags, _lineage, _semantics, _store


class _Alpha:
    def __init__(self, formula: str) -> None:
        self.meta = {"formula_latex": formula}


class _Registry:
    def __init__(self) -> None:
        self.items = {"safe": _Alpha("rank(close)"), "opaque": _Alpha(r"\\mathrm{rank}(close)")}

    def list(self) -> list[str]:
        return sorted(self.items)

    def get(self, alpha_id: str) -> _Alpha:
        return self.items[alpha_id]

    def get_source(self, alpha_id: str) -> str:
        return f"def {alpha_id}(): return 1"


def test_registry_bootstrap_uses_runtime_registry_without_fixed_count(tmp_path) -> None:
    store = _store(tmp_path)
    service = FactorDAGService(store=store, flags=_flags())
    event = service.bootstrap_registry(_Registry(), run_id="run-bootstrap")
    projection = service.projection()
    payload = build_registry_bootstrap_payload(_Registry())

    assert event.event_type == "RegistryBootstrapRecordedV2"
    assert len(projection.registry_roots) == len(_Registry().list())
    assert payload["roots"][0]["alpha_id"] == "opaque"
    assert {root.status for root in projection.registry_roots.values()} == {"canonical_dsl", "legacy_opaque"}
    assert {root.source_status for root in projection.registry_roots.values()} == {"available"}
    retried = service.bootstrap_registry(_Registry(), run_id="run-bootstrap")
    assert retried.event_hash == event.event_hash
    assert all("source" not in root for root in event.payload["roots"])


def test_registry_bootstrap_uses_the_supplied_grammar_and_rebuilds_hashes(tmp_path) -> None:
    store = _store(tmp_path)
    service = FactorDAGService(store=store, flags=_flags())
    grammar = DEFAULT_GRAMMAR.with_semantic_version("1.1.0")
    payload = build_registry_bootstrap_payload(_Registry(), grammar=grammar)
    safe = next(root for root in payload["roots"] if root["alpha_id"] == "safe")

    assert safe["expression_id"] == build_expression_identity("rank(close)", grammar=grammar).expression_id
    assert safe["expression_id"] != build_expression_identity("rank(close)").expression_id
    event = service.bootstrap_registry(_Registry(), run_id="run-custom", grammar=grammar)
    assert event.payload["grammar_hash"] == grammar.content_hash

    tampered = build_registry_bootstrap_payload(_Registry(), grammar=grammar)
    tampered["roots"][1]["expression_id"] = "sha256:" + "0" * 64
    with pytest.raises(EventValidationError, match="not reproducible"):
        store.append_event(
            EventDraft(
                event_type="RegistryBootstrapRecordedV2",
                entity_id=str(tampered["snapshot_id"]), run_id="run-tampered",
                payload_schema_version="registry_bootstrap_recorded.v2", payload=tampered,
            )
        )

    forged = event.to_dict()
    forged["payload"]["roots"][1]["expression_id"] = "sha256:" + "0" * 64
    forged["payload_hash"] = canonical_json_hash(forged["payload"])
    forged.pop("event_hash")
    forged["event_hash"] = canonical_json_hash(forged)
    with pytest.raises(FactorDAGError, match="not reproducible"):
        FactorDAGProjector(flags=_flags()).project(
            [ResearchEventEnvelope.from_dict(forged)]
        )


def test_registry_duplicate_ids_fail_instead_of_being_silently_collapsed() -> None:
    class DuplicateRegistry(_Registry):
        def list(self) -> list[str]:
            return ["safe", "safe"]

    with pytest.raises(ValueError, match="duplicate alpha IDs"):
        build_registry_bootstrap_payload(DuplicateRegistry())


def test_replay_rebuilds_identical_projection_state_hash(tmp_path) -> None:
    store, dag, _, _, _ = _lineage(tmp_path)
    projector = FactorDAGProjector(flags=_flags())

    assert projector.project(store.query_events()).projection_hash == dag.projection().projection_hash


def test_projection_resume_from_watermark_matches_full_replay(tmp_path) -> None:
    store, dag, _, _, _ = _lineage(tmp_path)
    projector = FactorDAGProjector(flags=_flags())
    events = store.query_events()
    checkpoint = projector.project(events[:4])
    resumed = projector.resume(events, checkpoint)
    full = dag.projection()

    assert resumed.projection_hash == full.projection_hash
    assert resumed.source_watermark_event_hash == full.source_watermark_event_hash


def test_projection_rejects_reordered_source_chain(tmp_path) -> None:
    store, _, _, _, _ = _lineage(tmp_path)
    events = store.query_events()
    events[0], events[1] = events[1], events[0]

    with pytest.raises(FactorDAGError, match="out of order"):
        FactorDAGProjector(flags=_flags()).project(events)


def test_depth_projection_is_iterative_for_long_audit_lineage() -> None:
    digest = "sha256:" + "a" * 64
    nodes = {
        f"factor-{index}": FactorNode(
            factor_spec_id=f"factor-{index}", expression_id=f"expression-{index}",
            canonical_ast_hash=digest, grammar_version="1.0.0", grammar_hash=digest,
            originating_trial_id=f"trial-{index}", definition_event_hash=digest,
        )
        for index in range(2_000)
    }
    edges = tuple(
        DerivationEdge(
            child_factor_spec_id=f"factor-{index}",
            parent_factor_spec_ids=(f"factor-{index - 1}",),
            trial_terminal_event_hash=digest, derivation_kind="mutation", event_hash=digest,
        )
        for index in range(1, 2_000)
    )

    assert _depths(nodes, edges)["factor-1999"] == 1_999
