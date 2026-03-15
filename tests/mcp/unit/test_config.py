# SPDX-License-Identifier: MIT

from pathlib import Path

from spx_mcp.config import SpxMcpConfig, normalize_base_url, python_supports_mcp


def test_normalize_base_url_strips_trailing_slash() -> None:
    assert normalize_base_url("http://localhost:8000/") == "http://localhost:8000"


def test_python_supports_mcp_respects_minimum_version() -> None:
    assert python_supports_mcp((3, 10, 0)) is True
    assert python_supports_mcp((3, 9, 12)) is False


def test_config_from_sources_uses_defaults(monkeypatch) -> None:
    monkeypatch.setenv("SPX_BASE_URL", "http://example:8000/")
    monkeypatch.setenv("SPX_PRODUCT_KEY", "KEY-123")

    config = SpxMcpConfig.from_sources(repo_root=".")

    assert config.repo_root == Path(".").resolve()
    assert config.spx_base_url == "http://example:8000"
    assert config.product_key == "KEY-123"
    assert config.allow_write is False
