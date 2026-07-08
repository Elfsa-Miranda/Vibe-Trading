"""Secret redaction helpers for IRR-AGL records."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

REDACTED = "[REDACTED]"

_SECRET_KEY_FRAGMENTS = (
    "secret",
    "token",
    "api_key",
    "apikey",
    "password",
    "credential",
    "broker",
    "authorization",
    "cookie",
    "session",
    "private_key",
    "refresh_token",
    "access_token",
)

_BEARER_RE = re.compile(r"^\s*bearer\s+[A-Za-z0-9._~+/=-]{16,}\s*$", re.IGNORECASE)
_KEY_PREFIX_RE = re.compile(r"^\s*(sk|rk|pk|ghp|gho|ghu|github_pat)-[A-Za-z0-9_\-]{20,}\s*$", re.IGNORECASE)
_LONG_RANDOM_RE = re.compile(r"^(?=.*[A-Z])(?=.*[a-z])(?=.*\d)[A-Za-z0-9_\-+/=]{40,}$")
_INLINE_BEARER_RE = re.compile(r"\bbearer\s+[A-Za-z0-9._~+/=-]{16,}", re.IGNORECASE)
_INLINE_KEY_PREFIX_RE = re.compile(r"\b(sk|rk|pk|ghp|gho|ghu|github_pat)-[A-Za-z0-9_\-]{16,}\b", re.IGNORECASE)
_INLINE_KEY_VALUE_RE = re.compile(
    r"\b(api[_-]?key|token|password|credential|secret)\s*=\s*[^\s\]`)]+",
    re.IGNORECASE,
)
_PRIVATE_KEY_BLOCK_RE = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
    re.IGNORECASE | re.DOTALL,
)
_DANGEROUS_MARKDOWN_URL_RE = re.compile(r"javascript\s*:", re.IGNORECASE)


def redact_secrets(value: Any) -> Any:
    """Recursively redact secret-like keys and values."""
    if isinstance(value, Mapping):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if _key_is_secret_like(key_text):
                redacted[key_text] = REDACTED
            else:
                redacted[key_text] = redact_secrets(item)
        return redacted
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    if isinstance(value, tuple):
        return [redact_secrets(item) for item in value]
    if isinstance(value, str):
        redacted_text = redact_secret_text(value)
        if redacted_text != value:
            return redacted_text
        if _value_is_secret_like(value):
            return REDACTED
    return value


def redact_secret_text(value: str) -> str:
    """Redact secret-like substrings in free text."""
    redacted = _PRIVATE_KEY_BLOCK_RE.sub(REDACTED, value)
    redacted = _INLINE_BEARER_RE.sub(REDACTED, redacted)
    redacted = _INLINE_KEY_VALUE_RE.sub(lambda match: f"{match.group(1)}={REDACTED}", redacted)
    redacted = _INLINE_KEY_PREFIX_RE.sub(REDACTED, redacted)
    redacted = _DANGEROUS_MARKDOWN_URL_RE.sub("blocked-url:", redacted)
    return redacted


def _key_is_secret_like(key: str) -> bool:
    lowered = key.lower()
    return any(fragment in lowered for fragment in _SECRET_KEY_FRAGMENTS)


def _value_is_secret_like(value: str) -> bool:
    return bool(_BEARER_RE.match(value) or _KEY_PREFIX_RE.match(value) or _LONG_RANDOM_RE.match(value))
