from __future__ import annotations
from dataclasses import dataclass
from src.research_ledger.hash_utils import canonical_json_hash
@dataclass(frozen=True)
class RegimeDefinition:
 feature:str; boundary:float; fit_scope:str; seed:int; code_hash:str
 def __post_init__(self):
  if self.fit_scope not in {"train","exogenous"}:raise ValueError("regime must be fit on train or exogenous")
 @property
 def regime_hash(self)->str:return canonical_json_hash(self.__dict__)
 def apply(self,values:tuple[float,...])->tuple[bool,...]:return tuple(value>=self.boundary for value in values)
__all__=["RegimeDefinition"]
