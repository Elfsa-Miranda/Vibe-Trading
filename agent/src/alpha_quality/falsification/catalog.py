from __future__ import annotations
from dataclasses import dataclass
from typing import Literal
from src.research_ledger.hash_utils import canonical_json_hash

@dataclass(frozen=True)
class TestCapability:
 test_id:str; version:str; required_fields:tuple[str,...]; pit_required:bool; universes:tuple[str,...]; frequencies:tuple[str,...]; min_effective_n:int; estimators:tuple[str,...]; dependence_methods:tuple[str,...]; output_schema_hash:str; resource_bound:int; unavailable_reason:str|None=None
 def snapshot_hash(self)->str:return canonical_json_hash(self.__dict__)
 def availability(self,*,universe:str,frequency:str,effective_n:int,fields:set[str])->tuple[bool,str|None]:
  if self.unavailable_reason:return False,self.unavailable_reason
  if universe not in self.universes:return False,"UNSUPPORTED_UNIVERSE"
  if frequency not in self.frequencies:return False,"UNSUPPORTED_FREQUENCY"
  if effective_n<self.min_effective_n:return False,"INSUFFICIENT_EFFECTIVE_SAMPLE"
  if not set(self.required_fields)<=fields:return False,"REQUIRED_DATA_UNAVAILABLE"
  return True,None
TestCapability.__test__ = False
__all__=["TestCapability"]
