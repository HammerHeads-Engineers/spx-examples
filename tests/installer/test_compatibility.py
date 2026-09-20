# SPDX-License-Identifier: MIT

from __future__ import annotations

import pytest

from installer.compatibility import (
    SPX_SERVER_VERSION,
    SPX_UI_VERSION,
    validate_version_pair,
)


def test_supported_server_ui_pair_is_explicit() -> None:
    validate_version_pair(SPX_SERVER_VERSION, SPX_UI_VERSION)
    assert SPX_SERVER_VERSION == "v1.0.0-rc.64"
    assert SPX_UI_VERSION == "v1.0.0-rc.68"


def test_unsupported_server_ui_pair_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unsupported SPX Server/UI version pair"):
        validate_version_pair("v1.0.0-rc.63", SPX_UI_VERSION)
