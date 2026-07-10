from __future__ import annotations
import math
from src.alpha_foundry.dag.query import FactorDAGQuery
from src.alpha_foundry.retrieval.model import FactorOutputFeature

def leaf_likelihood(feature: FactorOutputFeature) -> tuple[float, tuple[str,...]]:
    values=feature.aligned_train_valid_outputs
    if len(values)<2: return 0.0,("MISSING_ALIGNED_FACTOR_OUTPUTS",)
    mean=sum(values)/len(values)
    variance=sum((v-mean)**2 for v in values)/len(values)
    valdiv=min(1.0, math.sqrt(variance))
    if feature.semantic_diversity is None: return 0.0,("MISSING_SEMANTIC_EMBEDDING",)
    if not 0<=feature.semantic_diversity<=1 or not 0<=feature.structural_diversity<=1: raise ValueError("diversity features must be bounded")
    return valdiv*feature.semantic_diversity*feature.structural_diversity,()

def nonleaf_score(feature: FactorOutputFeature, query: FactorDAGQuery) -> float:
    gain=feature.child_quality_gain
    if gain is None: return 0.0
    return max(0.0,gain)*query.branch_sparsity(feature.factor_spec_id)/(1+query.depth(feature.factor_spec_id))

__all__=["leaf_likelihood","nonleaf_score"]
