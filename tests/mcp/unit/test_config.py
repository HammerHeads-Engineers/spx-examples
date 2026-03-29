# SPDX-License-Identifier: MIT

from pathlib import Path

import json

from spx_mcp.config import (
    SpxMcpConfig,
    is_placeholder_product_key,
    normalize_base_url,
    python_supports_mcp,
)


def test_normalize_base_url_strips_trailing_slash() -> None:
    assert normalize_base_url("http://localhost:8000/") == "http://localhost:8000"


def test_python_supports_mcp_respects_minimum_version() -> None:
    assert python_supports_mcp((3, 10, 0)) is True
    assert python_supports_mcp((3, 9, 12)) is False


def test_config_from_sources_uses_defaults(monkeypatch) -> None:
    monkeypatch.setenv("SPX_BASE_URL", "http://example:8000/")
    monkeypatch.setenv("SPX_PRODUCT_KEY", "TEST-CLI-KEY")

    config = SpxMcpConfig.from_sources(repo_root=".")

    assert config.repo_root == Path(".").resolve()
    assert config.spx_base_url == "http://example:8000"
    assert config.product_key == "TEST-CLI-KEY"
    assert config.allow_write is False


def test_config_from_sources_reads_repo_dotenv(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("SPX_BASE_URL", raising=False)
    monkeypatch.delenv("SPX_PRODUCT_KEY", raising=False)
    (tmp_path / ".env").write_text(
        "SPX_BASE_URL=http://dotenv:8000/\nSPX_PRODUCT_KEY=TEST-DOTENV-KEY\n",
        encoding="utf-8",
    )

    config = SpxMcpConfig.from_sources(repo_root=str(tmp_path))

    assert config.repo_root == tmp_path.resolve()
    assert config.spx_base_url == "http://dotenv:8000"
    assert config.product_key == "TEST-DOTENV-KEY"


def test_placeholder_product_key_is_treated_as_missing(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("SPX_PRODUCT_KEY", raising=False)
    (tmp_path / ".env").write_text(
        "SPX_PRODUCT_KEY=REPLACE_ME\n",
        encoding="utf-8",
    )

    config = SpxMcpConfig.from_sources(repo_root=str(tmp_path))

    assert is_placeholder_product_key("REPLACE_ME") is True
    assert config.product_key is None
    assert config.product_key_status == "placeholder"
    assert config.has_valid_product_key is False


def test_config_from_sources_falls_back_to_managed_source_root_env(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("SPX_PRODUCT_KEY", raising=False)
    source_root = tmp_path / "source"
    source_root.mkdir()
    (source_root / ".env").write_text(
        "SPX_PRODUCT_KEY=TEST-SOURCE-KEY-123\n",
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text(
        "SPX_PRODUCT_KEY=REPLACE_ME\n",
        encoding="utf-8",
    )
    (tmp_path / ".spx-mcp-workspace.json").write_text(
        json.dumps(
            {
                "kind": "spx-codex-mcp-workspace",
                "workspace_kind": "managed",
                "default_work_mode": "runtime_mcp",
                "source_root": str(source_root),
            }
        ),
        encoding="utf-8",
    )

    config = SpxMcpConfig.from_sources(repo_root=str(tmp_path))

    assert config.product_key == "TEST-SOURCE-KEY-123"
    assert config.product_key_source == f"managed source_root .env ({source_root / '.env'})"
    assert config.workspace_kind == "managed"
    assert config.default_work_mode == "runtime_mcp"
