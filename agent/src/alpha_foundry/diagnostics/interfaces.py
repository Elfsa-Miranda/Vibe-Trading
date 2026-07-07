"""Stub-only diagnostics interface for Phase 2."""

from __future__ import annotations

from typing import Protocol

import pandas as pd


class FactorDiagnosticsConsumer(Protocol):
    def consume_factor_output(self, frame: pd.DataFrame) -> None: ...
