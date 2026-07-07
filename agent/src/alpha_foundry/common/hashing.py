"""Canonical JSON and hash helpers for Alpha Foundry artifacts."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel


def canonical_json(obj: BaseModel | dict[str, Any], *, exclude_schema_version: bool = True) -> str:
    payload = obj.model_dump(mode="json") if isinstance(obj, BaseModel) else obj
    if exclude_schema_version:
        payload = {k: v for k, v in payload.items() if k != "schema_version"}
    return json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )


def canonical_hash(obj: BaseModel | dict[str, Any], *, exclude_schema_version: bool = True) -> str:
    canonical = canonical_json(obj, exclude_schema_version=exclude_schema_version)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

