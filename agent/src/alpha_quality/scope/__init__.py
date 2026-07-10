"""Capability-specific scope isolation primitives."""

from src.alpha_quality.scope.capabilities import (
    FinalScopeViolation,
    TestScopeAuthority,
    TestScopeCapability,
)
from src.alpha_quality.scope.views import DiscoveryEvidenceProjector

__all__ = [
    "DiscoveryEvidenceProjector",
    "FinalScopeViolation",
    "TestScopeAuthority",
    "TestScopeCapability",
]
