"""ComplementEvidence.v2 public surface."""

from src.alpha_quality.complement.engine import ComplementEngine, ComplementInputs
from src.alpha_quality.complement.identity import (
    FactorIdentityRecord,
    build_duplicate_identity_evidence,
)
from src.alpha_quality.complement.model import (
    ComplementEvidenceV2,
    ComplementPolicy,
    CorrelationEvidence,
    DuplicateIdentityEvidence,
    PortfolioComplementEvidence,
    ResidualComplementEvidence,
)
from src.alpha_quality.complement.portfolio import compute_portfolio_complement
from src.alpha_quality.complement.residual import compute_residual_complement
from src.alpha_quality.complement.service import (
    ComplementEvidenceService,
    RecordedComplementEvidence,
)

__all__ = [
    "ComplementEngine",
    "ComplementEvidenceService",
    "ComplementEvidenceV2",
    "ComplementInputs",
    "ComplementPolicy",
    "CorrelationEvidence",
    "DuplicateIdentityEvidence",
    "FactorIdentityRecord",
    "PortfolioComplementEvidence",
    "ResidualComplementEvidence",
    "RecordedComplementEvidence",
    "build_duplicate_identity_evidence",
    "compute_portfolio_complement",
    "compute_residual_complement",
]
