from __future__ import annotations
from src.alpha_quality.falsification.catalog import TestCapability
from src.alpha_quality.falsification.contract import FalsificationContract
def validate_contract(contract:FalsificationContract, capability:TestCapability)->None:
 if contract.capability_hash!=capability.snapshot_hash():raise ValueError("contract capability snapshot mismatch")
 if contract.dependence_method not in capability.dependence_methods:raise ValueError("dependence method unavailable")
__all__=["validate_contract"]
