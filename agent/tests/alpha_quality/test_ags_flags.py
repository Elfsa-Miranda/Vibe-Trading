from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from src.alpha_quality.flags import AGS_FLAG_DEFAULTS, ResolvedAGSFlags


def test_all_ags_flags_default_false_and_master_flag_dominates() -> None:
    flags = ResolvedAGSFlags.from_settings(
        {
            "VIBE_TRADING_FACTOR_DAG": "true",
            "VIBE_TRADING_ALPHA_REPORT_API": "1",
        }
    )

    assert len(AGS_FLAG_DEFAULTS) == 14
    assert set(flags.as_dict()) == set(AGS_FLAG_DEFAULTS)
    assert not any(flags.as_dict().values())

    enabled = ResolvedAGSFlags.from_settings(
        {
            "VIBE_TRADING_AGS_ENABLED": "yes",
            "VIBE_TRADING_FACTOR_DAG": "on",
        }
    )
    assert enabled.enabled("VIBE_TRADING_AGS_ENABLED")
    assert enabled.enabled("VIBE_TRADING_FACTOR_DAG")
    assert not enabled.enabled("VIBE_TRADING_ALPHA_REPORT_API")


def test_flag_snapshot_is_immutable_until_app_is_recreated() -> None:
    settings = {
        "VIBE_TRADING_AGS_ENABLED": "1",
        "VIBE_TRADING_ALPHA_REPORT_API": "1",
    }
    flags = ResolvedAGSFlags.from_settings(settings)
    settings["VIBE_TRADING_ALPHA_REPORT_API"] = "0"

    assert flags.enabled("VIBE_TRADING_ALPHA_REPORT_API")
    with pytest.raises(TypeError):
        flags.values["VIBE_TRADING_ALPHA_REPORT_API"] = False  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        flags.values = {}  # type: ignore[misc]


def test_unknown_flag_is_rejected() -> None:
    flags = ResolvedAGSFlags.from_settings({})

    with pytest.raises(KeyError, match="unknown AGS feature flag"):
        flags.enabled("VIBE_TRADING_NOT_A_REAL_FLAG")
