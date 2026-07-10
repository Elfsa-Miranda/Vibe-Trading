from __future__ import annotations
from dataclasses import dataclass
from src.research_ledger.hash_utils import canonical_json_hash
@dataclass(frozen=True)
class FalsificationContract:
 factor_spec_id:str; capability_hash:str; estimand:str; direction:str; sesoi:float; units:str; sample_unit:str; conditioning_hash:str; regime_hash:str; family_id:str; alpha:float; dependence_method:str; maximum_looks:int; stopping_rule:str; decisive:bool; policy_hash:str
 def __post_init__(self):
  if self.sesoi<=0 or not 0<self.alpha<1 or self.maximum_looks<1:raise ValueError("invalid frozen falsification contract")
 @property
 def contract_hash(self)->str:return canonical_json_hash(self.__dict__)
 @property
 def contract_id(self)->str:return "contract-"+self.contract_hash.removeprefix("sha256:")[:16]
__all__=["FalsificationContract"]
