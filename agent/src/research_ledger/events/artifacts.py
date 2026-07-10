"""Content-addressed artifact reference validation outside write transactions."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path, PurePosixPath
from typing import Any, Mapping
from urllib.parse import unquote

from src.research_ledger.events.model import ArtifactReferenceError


_WINDOWS_ABSOLUTE_RE = re.compile(r"^(?:[A-Za-z]:|\\\\|//|\\[?.]\\)")
_ADS_RE = re.compile(r"^[^/]+:[^/]+")


def hash_artifact(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _safe_relative_path(raw: str) -> PurePosixPath:
    if not isinstance(raw, str) or not raw or "\x00" in raw:
        raise ArtifactReferenceError("invalid relative artifact path")
    if unquote(raw) != raw:
        raise ArtifactReferenceError("encoded relative artifact path is forbidden")
    if "\\" in raw or _WINDOWS_ABSOLUTE_RE.match(raw) or _ADS_RE.match(raw):
        raise ArtifactReferenceError("invalid relative artifact path")
    relative = PurePosixPath(raw)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise ArtifactReferenceError("invalid relative artifact path")
    return relative


def validate_artifact_references(
    artifact_root: str | Path,
    references: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...],
) -> list[dict[str, str]]:
    root = Path(artifact_root).resolve(strict=True)
    normalized: list[dict[str, str]] = []
    for reference in references:
        relative = _safe_relative_path(str(reference["relative_path"]))
        candidate = root.joinpath(*relative.parts)
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(root)
        except (FileNotFoundError, OSError, ValueError) as exc:
            raise ArtifactReferenceError(
                f"artifact is missing or escapes artifact root: {relative.as_posix()}"
            ) from exc
        if not resolved.is_file():
            raise ArtifactReferenceError(f"artifact is not a regular file: {relative.as_posix()}")
        actual_hash = hash_artifact(resolved)
        expected_hash = str(reference["artifact_hash"])
        if actual_hash != expected_hash:
            raise ArtifactReferenceError(
                f"artifact hash mismatch for {relative.as_posix()}"
            )
        normalized.append(
            {
                "relative_path": relative.as_posix(),
                "artifact_hash": expected_hash,
                "media_type": str(reference["media_type"]),
            }
        )
    return normalized


__all__ = ["hash_artifact", "validate_artifact_references"]
