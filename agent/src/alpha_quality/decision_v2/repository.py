"""Content-addressed repository for closed Decision v2 evidence records."""

from __future__ import annotations

import json
from pathlib import Path

from src.alpha_quality.decision_v2.model import (
    DecisionEvidenceRecord,
    EvidenceKind,
)
from src.research_ledger.hash_utils import canonical_json


class EvidenceResolutionError(RuntimeError):
    """Raised when a cited immutable evidence record is absent or invalid."""


class DecisionEvidenceRepository:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.root = self.root.resolve(strict=True)

    def put(self, record: DecisionEvidenceRecord) -> str:
        if not isinstance(record, DecisionEvidenceRecord):
            raise TypeError("a typed DecisionEvidenceRecord is required")
        path = self._path(record.evidence_hash)
        encoded = canonical_json(record.to_dict())
        if path.exists():
            if path.read_text(encoding="utf-8") != encoded:
                raise EvidenceResolutionError("content-addressed evidence collision")
            return record.evidence_hash
        temporary = path.with_suffix(".tmp")
        temporary.write_text(encoded, encoding="utf-8")
        temporary.replace(path)
        return record.evidence_hash

    def resolve(
        self,
        evidence_hash: str,
        *,
        expected_kind: EvidenceKind,
        factor_spec_id: str,
    ) -> DecisionEvidenceRecord:
        path = self._path(evidence_hash)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            record = DecisionEvidenceRecord(
                schema_version=raw["schema_version"],
                evidence_kind=raw["evidence_kind"],
                factor_spec_id=raw["factor_spec_id"],
                payload=raw["payload"],
                evidence_hash=raw["evidence_hash"],
            )
        except (FileNotFoundError, OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise EvidenceResolutionError("decision evidence is missing, malformed, or tampered") from exc
        if record.evidence_hash != evidence_hash:
            raise EvidenceResolutionError("decision evidence filename/hash mismatch")
        if record.evidence_kind != expected_kind:
            raise EvidenceResolutionError("decision evidence kind mismatch")
        if record.factor_spec_id != factor_spec_id:
            raise EvidenceResolutionError("decision evidence factor mismatch")
        return record

    def _path(self, evidence_hash: str) -> Path:
        if not evidence_hash.startswith("sha256:") or len(evidence_hash) != 71:
            raise EvidenceResolutionError("invalid decision evidence hash")
        filename = evidence_hash.removeprefix("sha256:") + ".json"
        path = (self.root / filename).resolve(strict=False)
        try:
            path.relative_to(self.root)
        except ValueError as exc:
            raise EvidenceResolutionError("decision evidence path escapes root") from exc
        return path


__all__ = ["DecisionEvidenceRepository", "EvidenceResolutionError"]
