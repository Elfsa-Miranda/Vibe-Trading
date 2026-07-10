from __future__ import annotations
from src.alpha_quality.falsification.contract import FalsificationContract
from src.alpha_quality.flags import ResolvedAGSFlags
from src.research_ledger.events import EventDraft,ResearchEventStore
from src.research_ledger.hash_utils import utc_now_iso
class FalsificationService:
 def __init__(self,*,store:ResearchEventStore,flags:ResolvedAGSFlags):
  if not flags.enabled("VIBE_TRADING_FALSIFICATION_CONTRACT"):raise RuntimeError("falsification contract capability is disabled")
  self.store=store
 def register(self,contract:FalsificationContract,*,run_id:str):
  prior_access=self.store.query_events(event_type="OutcomeDataAccessed")
  if any(event.payload["factor_spec_id"]==contract.factor_spec_id for event in prior_access):raise ValueError("outcome data was accessed before contract registration")
  now=utc_now_iso();return self.store.append_event(EventDraft(event_type="FalsificationContractRegistered",entity_id=contract.contract_id,run_id=run_id,payload_schema_version="falsification_contract_registered.v1",idempotency_key="contract:"+contract.contract_hash,payload={"contract_id":contract.contract_id,"contract_hash":contract.contract_hash,"factor_spec_id":contract.factor_spec_id,"registered_at":now,"data_access_cutoff":now,"policy_hash":contract.policy_hash}))
 def outcome_access(self,contract:FalsificationContract)->None:
  registered=self.store.query_events(event_type="FalsificationContractRegistered",entity_id=contract.contract_id)
  if not registered:
   access_id="access-"+contract.factor_spec_id
   self.store.append_event(EventDraft(event_type="OutcomeDataAccessed",entity_id=access_id,run_id="falsification-access",payload_schema_version="outcome_data_accessed.v1",idempotency_key="outcome-access:"+contract.factor_spec_id,payload={"access_id":access_id,"factor_spec_id":contract.factor_spec_id,"data_scope":"valid","accessed_at":utc_now_iso()}))
   raise ValueError("outcome access requires registered contract")
__all__=["FalsificationService"]
