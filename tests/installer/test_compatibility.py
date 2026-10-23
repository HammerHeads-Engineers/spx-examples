# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from installer.compatibility import (
    SPX_SERVER_VERSION,
    SPX_UI_VERSION,
    validate_version_pair,
)


def test_supported_server_ui_pair_is_explicit() -> None:
    validate_version_pair(SPX_SERVER_VERSION, SPX_UI_VERSION)
    assert SPX_SERVER_VERSION == "v1.0.0-rc.74"
    assert SPX_UI_VERSION == "v1.0.0-rc.75"


def test_unsupported_server_ui_pair_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unsupported SPX Server/UI version pair"):
        validate_version_pair("v1.0.0-rc.63", SPX_UI_VERSION)


def test_root_compose_uses_supported_server_version() -> None:
    compose_path = Path(__file__).resolve().parents[2] / "docker-compose.yml"
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    assert compose["services"]["spx-server"]["image"] == (
        f"simplephysx/spx-server:{SPX_SERVER_VERSION}"
    )
