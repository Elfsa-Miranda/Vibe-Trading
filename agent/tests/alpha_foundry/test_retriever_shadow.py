from __future__ import annotations
import pytest
from src.alpha_foundry.dag import FactorDAGQuery,FactorDAGProjector
from src.alpha_foundry.retrieval import DiscoveryEvidenceView,FactorOutputFeature,ShadowRetriever
from src.alpha_quality.flags import ResolvedAGSFlags
from src.research_ledger.hash_utils import canonical_json_hash
from test_factor_dag import _lineage

def _flags(): return ResolvedAGSFlags.from_settings({"VIBE_TRADING_AGS_ENABLED":"1","VIBE_TRADING_TOPOLOGY_RETRIEVER":"1"})
def _retriever(): return ShadowRetriever(flags=_flags(),policy_hash=canonical_json_hash({"policy":"shadow.v1"}))
def test_probe_leaf_likelihood_is_not_an_admission_gate_and_uses_outputs(tmp_path):
 store,dag,parent,child,_=_lineage(tmp_path); query=FactorDAGQuery(dag.projection())
 decision=_retriever().decide(official_candidate_ids=("legacy",),evidence=DiscoveryEvidenceView(store.replay().watermark_event_hash),query=query,features=(FactorOutputFeature(parent,(0.0,1.0),0.5,0.5),),episodic=__import__('src.alpha_foundry.memory.model',fromlist=['EpisodicProjection']).EpisodicProjection("episodic_process_projection.v1",None,(),(),canonical_json_hash({})),seed=9)
 assert decision.selected_factor_spec_ids==(parent,)
 assert decision.components[0][1] >= 0
def test_shadow_does_not_change_official_inputs_and_missing_embedding_is_explicit(tmp_path):
 store,dag,parent,child,_=_lineage(tmp_path); query=FactorDAGQuery(dag.projection()); official=("a","b")
 empty=__import__('src.alpha_foundry.memory.model',fromlist=['EpisodicProjection']).EpisodicProjection("episodic_process_projection.v1",None,(),(),canonical_json_hash({}))
 decision=_retriever().decide(official_candidate_ids=official,evidence=DiscoveryEvidenceView(None),query=query,features=(FactorOutputFeature(parent,(1.,2.),None,.5),),episodic=empty,seed=3)
 assert official==("a","b") and decision.components[0][2]==("MISSING_SEMANTIC_EMBEDDING",)
def test_final_view_and_flag_off_are_rejected():
 with pytest.raises(ValueError): DiscoveryEvidenceView(None,scope="final")
 with pytest.raises(RuntimeError): ShadowRetriever(flags=ResolvedAGSFlags.from_settings({"VIBE_TRADING_AGS_ENABLED":"1"}),policy_hash=canonical_json_hash({}))
