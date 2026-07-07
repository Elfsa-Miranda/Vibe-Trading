from __future__ import annotations

import pytest

from tests.alpha_foundry.fixtures.factory import make_factor_output_frame


@pytest.fixture
def factor_output_frame():
    return make_factor_output_frame()
