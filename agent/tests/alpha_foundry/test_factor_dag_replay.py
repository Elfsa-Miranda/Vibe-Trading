from __future__ import annotations

from src.alpha_foundry.dag import FactorDAGProjector, FactorDAGService
from src.alpha_foundry.dag.bootstrap import build_registry_bootstrap_payload
from src.alpha_foundry.dsl.identity import FactorIdentityService

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


def test_registry_bootstrap_uses_runtime_registry_without_fixed_count(tmp_path) -> None:
    store = _store(tmp_path)
    service = FactorDAGService(store=store, flags=_flags())
    event = service.bootstrap_registry(_Registry(), run_id="run-bootstrap")
    projection = service.projection()
    payload = build_registry_bootstrap_payload(_Registry())

    assert event.event_type == "RegistryBootstrapRecorded"
    assert len(projection.registry_roots) == len(_Registry().list())
    assert payload["roots"][0]["alpha_id"] == "opaque"
    assert {root.status for root in projection.registry_roots.values()} == {"canonical_dsl", "legacy_opaque"}


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
