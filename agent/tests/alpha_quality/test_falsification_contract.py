from __future__ import annotations
import pytest
from src.alpha_quality.falsification import TestCapability,FalsificationContract,validate_contract,FalsificationService
from src.alpha_quality.flags import ResolvedAGSFlags
from src.research_ledger.events import ResearchEventStore
from src.research_ledger.hash_utils import canonical_json_hash
def _cap():return TestCapability("placebo","v1",("close",),True,("equity_cn",),("1d",),20,("mean",),("hac",),canonical_json_hash({"out":"v1"}),10)
def _contract(**changes):
 d=dict(factor_spec_id="f",capability_hash=_cap().snapshot_hash(),estimand="ic",direction="positive",sesoi=.01,units="ic",sample_unit="date",conditioning_hash=canonical_json_hash({}),regime_hash=canonical_json_hash({}),family_id="family",alpha=.05,dependence_method="hac",maximum_looks=1,stopping_rule="fixed",decisive=True,policy_hash=canonical_json_hash({"p":1}));d.update(changes);return FalsificationContract(**d)
def test_contract_hash_changes_when_margin_family_or_stopping_rule_changes():
 base=_contract();assert len({_contract(sesoi=.02).contract_hash,_contract(family_id="other").contract_hash,_contract(stopping_rule="seq",maximum_looks=2).contract_hash,base.contract_hash})==4
def test_catalog_unavailability_and_validator_fail_closed():
 cap=_cap();assert cap.availability(universe="equity_cn",frequency="1d",effective_n=2,fields={"close"})==(False,"INSUFFICIENT_EFFECTIVE_SAMPLE")
 with pytest.raises(ValueError):validate_contract(_contract(dependence_method="iid"),cap)
def test_contract_is_committed_before_any_outcome_access(tmp_path):
 flags=ResolvedAGSFlags.from_settings({"VIBE_TRADING_AGS_ENABLED":"1","VIBE_TRADING_RESEARCH_EVENTS":"1","VIBE_TRADING_FALSIFICATION_CONTRACT":"1"});store=ResearchEventStore(tmp_path/"db.sqlite",artifact_root=tmp_path/"a",flags=flags,code_version="test");service=FalsificationService(store=store,flags=flags);contract=_contract()
 with pytest.raises(ValueError):service.outcome_access(contract)
 with pytest.raises(ValueError):service.register(contract,run_id="r")
