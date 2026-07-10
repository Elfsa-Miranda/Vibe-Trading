"""The only write-facing convenience boundary for validated DAG events."""

from __future__ import annotations

from src.alpha_foundry.dag.bootstrap import RegistryBootstrapSource, build_registry_bootstrap_payload
from src.alpha_foundry.dag.projector import FactorDAGProjector
from src.alpha_foundry.dsl.grammar import DEFAULT_GRAMMAR, GrammarDefinition
from src.alpha_quality.flags import ResolvedAGSFlags
from src.research_ledger.events import EventDraft, ResearchEventStore
from src.research_ledger.hash_utils import canonical_json_hash


class FactorDAGService:
    """Validate against the current derived projection before appending events."""

    def __init__(self, *, store: ResearchEventStore, flags: ResolvedAGSFlags) -> None:
        required = (
            "VIBE_TRADING_ALPHA_FOUNDRY", "VIBE_TRADING_RESEARCH_EVENTS",
            "VIBE_TRADING_FACTOR_DAG",
        )
        if any(not flags.enabled(name) for name in required):
            raise RuntimeError("factor DAG capability is disabled")
        self.store = store
        self.projector = FactorDAGProjector(flags=flags)

    def projection(self):
        return self.projector.project(self.store.query_events())

    def bootstrap_registry(
        self, registry: RegistryBootstrapSource, *, run_id: str,
        grammar: GrammarDefinition = DEFAULT_GRAMMAR,
    ):
        payload = build_registry_bootstrap_payload(registry, grammar=grammar)
        return self.store.append_event(
            EventDraft(
                event_type="RegistryBootstrapRecordedV2",
                entity_id=str(payload["snapshot_id"]),
                run_id=run_id,
                payload_schema_version="registry_bootstrap_recorded.v2",
                payload=payload,
                idempotency_key="registry-bootstrap:" + str(payload["registry_snapshot_hash"]),
            )
        )

    def record_derivation(
        self,
        *,
        child_factor_spec_id: str,
        parent_factor_spec_ids: list[str] | tuple[str, ...],
        trial_terminal_event_hash: str,
        derivation_kind: str,
        run_id: str,
    ):
        parents = list(parent_factor_spec_ids)
        payload = {
            "child_factor_spec_id": child_factor_spec_id,
            "parent_factor_spec_ids": parents,
            "trial_terminal_event_hash": trial_terminal_event_hash,
            "derivation_kind": derivation_kind,
        }
        # Feed a synthetic envelope-free payload through the same projector
        # invariant checks by asserting the current graph properties locally.
        projection = self.projection()
        if child_factor_spec_id not in projection.factor_nodes:
            raise ValueError("derivation child has no prior factor definition")
        if not parents or any(parent not in projection.factor_nodes for parent in parents):
            raise ValueError("derivation parent has no prior factor definition")
        if child_factor_spec_id in parents:
            raise ValueError("lineage self-edge is forbidden")
        if len(set(parents)) != len(parents):
            raise ValueError("derivation contains duplicate parent")
        if any(edge.child_factor_spec_id == child_factor_spec_id for edge in projection.derivation_edges):
            raise ValueError("multiple lineage derivations for one child are ambiguous")
        for parent in parents:
            if parent in self._descendants(projection, child_factor_spec_id):
                raise ValueError("derivation creates a lineage cycle")
        edge_hash = canonical_json_hash(payload)
        return self.store.append_event(
            EventDraft(
                event_type="DerivationRecorded",
                entity_id=child_factor_spec_id,
                run_id=run_id,
                payload_schema_version="derivation_recorded.v1",
                payload=payload,
                idempotency_key=f"derivation:{edge_hash}",
            )
        )

    @staticmethod
    def _descendants(projection, factor_spec_id: str) -> set[str]:
        children: dict[str, set[str]] = {}
        for edge in projection.derivation_edges:
            for parent in edge.parent_factor_spec_ids:
                children.setdefault(parent, set()).add(edge.child_factor_spec_id)
        pending = list(children.get(factor_spec_id, ()))
        seen: set[str] = set()
        while pending:
            node = pending.pop()
            if node in seen:
                continue
            seen.add(node)
            pending.extend(children.get(node, ()))
        return seen


__all__ = ["FactorDAGService"]
