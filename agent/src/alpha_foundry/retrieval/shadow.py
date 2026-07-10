from __future__ import annotations
from src.alpha_foundry.dag.query import FactorDAGQuery
from src.alpha_foundry.memory.model import EpisodicProjection
from src.alpha_foundry.retrieval.features import leaf_likelihood, nonleaf_score
from src.alpha_foundry.retrieval.model import DiscoveryEvidenceView, FactorOutputFeature, ShadowDecision
from src.alpha_quality.flags import ResolvedAGSFlags
from src.research_ledger.events import EventDraft, ResearchEventStore
from src.research_ledger.hash_utils import canonical_json_hash

class ShadowRetriever:
 def __init__(self, *, flags: ResolvedAGSFlags, policy_hash: str):
  if not flags.enabled("VIBE_TRADING_TOPOLOGY_RETRIEVER"): raise RuntimeError("topology retriever capability is disabled")
  self.policy_hash=policy_hash
 def decide(self, *, official_candidate_ids: tuple[str,...], evidence: DiscoveryEvidenceView, query: FactorDAGQuery, features: tuple[FactorOutputFeature,...], episodic: EpisodicProjection, seed: int) -> ShadowDecision:
  # Does not mutate or consume any official RNG/candidate object.
  components=[]; veto=None
  posteriors={(p.parent_context_hash,p.motif):p for p in episodic.posteriors}
  for feature in features:
   if feature.factor_spec_id not in query.projection.factor_nodes: continue
   leaf, warnings=leaf_likelihood(feature)
   score=nonleaf_score(feature,query) if query.descendants(feature.factor_spec_id) else leaf
   for posterior in posteriors.values():
    if posterior.hard_veto: veto="HIGH_CONFIDENCE_NEGATIVE_MEMORY"; score=float("-inf")
    else: score+=posterior.positive_adjustment
   components.append((feature.factor_spec_id,score,warnings))
  ranked=tuple(item[0] for item in sorted(components,key=lambda x:(-x[1],x[0])) if item[1]!=float("-inf"))
  return ShadowDecision(ranked, 1.0/max(1,len(ranked)), seed, self.policy_hash, evidence.source_watermark, veto, tuple(components))
 def record(self, store: ResearchEventStore, decision: ShadowDecision, *, run_id: str):
  identifier="retriever-"+canonical_json_hash({"ids":decision.selected_factor_spec_ids,"seed":decision.seed,"policy":decision.policy_hash}).removeprefix("sha256:")[:16]
  return store.append_event(EventDraft(event_type="RetrieverDecisionRecorded",entity_id=identifier,run_id=run_id,payload_schema_version="retriever_decision_recorded.v1",idempotency_key="retriever:"+identifier,payload={"decision_id":identifier,"selected_factor_spec_ids":list(decision.selected_factor_spec_ids),"selection_propensity":decision.selection_propensity,"seed":decision.seed,"policy_hash":decision.policy_hash,"eligible_event_watermark":decision.eligible_event_watermark,"veto_reason":decision.veto_reason}))
__all__=["ShadowRetriever"]
