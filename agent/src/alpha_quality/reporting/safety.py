from __future__ import annotations

import os
import re
import stat
from pathlib import Path
from urllib.parse import unquote


class ReportPathError(ValueError):
    """Raised when a report reference is not a root-contained regular file."""


_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,160}$")
_DRIVE_OR_DEVICE_RE = re.compile(r"(?i)^(?:[a-z]:|\\\\[?.]\\|//[?.]/|\\\\|//)")
_SUSPICIOUS_DOTS = {"\u2024", "\u2025", "\u2026", "\uff0e"}
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


def _decode(value: str) -> str:
    decoded = value
    for _ in range(4):
        next_value = unquote(decoded)
        if next_value == decoded:
            return decoded
        decoded = next_value
    return decoded


def _is_reparse_point(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    if callable(is_junction) and is_junction():
        return True
    try:
        return bool(getattr(path.lstat(), "st_file_attributes", 0) & _REPARSE_POINT)
    except FileNotFoundError:
        return False


def validate_report_name(value: str) -> str:
    decoded = _decode(value)
    if (
        not _SAFE_NAME_RE.fullmatch(decoded)
        or "\x00" in decoded
        or any(char in decoded for char in _SUSPICIOUS_DOTS)
        or ":" in decoded
        or "/" in decoded
        or "\\" in decoded
        or _DRIVE_OR_DEVICE_RE.match(decoded)
    ):
        raise ReportPathError("invalid report artifact name")
    return decoded


def resolve_report_file(root: str | Path, filename: str) -> Path:
    safe_name = validate_report_name(filename)
    root_path = Path(root)
    if not root_path.exists() or not root_path.is_dir() or _is_reparse_point(root_path):
        raise ReportPathError("report artifact root is unavailable")
    resolved_root = root_path.resolve(strict=True)
    target = resolved_root / safe_name
    try:
        target.relative_to(resolved_root)
    except ValueError as exc:
        raise ReportPathError("invalid report artifact path") from exc
    if not target.exists():
        return target
    if _is_reparse_point(target) or not target.is_file():
        raise ReportPathError("report artifact is not a regular contained file")
    resolved_target = target.resolve(strict=True)
    try:
        resolved_target.relative_to(resolved_root)
    except ValueError as exc:
        raise ReportPathError("report artifact escaped its root") from exc
    if os.path.normcase(str(resolved_target.parent)) != os.path.normcase(str(resolved_root)):
        raise ReportPathError("report artifact parent mismatch")
    return resolved_target
