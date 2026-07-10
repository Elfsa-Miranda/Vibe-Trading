from __future__ import annotations

import pytest

from src.alpha_quality.falsification.multiplicity import adjust


def test_holm_bh_and_by_match_reference_fixtures() -> None:
    pvalues = [0.01, 0.04, 0.03]
    assert adjust(pvalues, "holm") == pytest.approx([0.03, 0.06, 0.06])
    assert adjust(pvalues, "bh") == pytest.approx([0.03, 0.04, 0.04])
    assert adjust(pvalues, "by") == pytest.approx([0.055, 0.0733333333, 0.0733333333])


def test_invalid_pvalues_and_unknown_method_fail_closed() -> None:
    with pytest.raises(ValueError, match="finite probabilities"):
        adjust([float("nan")], "holm")
    with pytest.raises(ValueError, match="unsupported"):
        adjust([0.1], "sidak")  # type: ignore[arg-type]
