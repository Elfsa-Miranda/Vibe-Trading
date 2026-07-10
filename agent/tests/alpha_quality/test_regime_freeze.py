from __future__ import annotations
import pytest
from src.alpha_quality.falsification import RegimeDefinition
from src.research_ledger.hash_utils import canonical_json_hash
def test_regime_config_is_fit_on_train_and_frozen_before_validation():
 regime=RegimeDefinition("vol",1.0,"train",7,canonical_json_hash({"code":"v1"}));assert regime.apply((.5,1.5))==(False,True)
 with pytest.raises(ValueError):RegimeDefinition("vol",1.,"train_valid",7,canonical_json_hash({}))
