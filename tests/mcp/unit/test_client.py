# SPDX-License-Identifier: MIT

from pathlib import Path

import pytest

from spx_mcp.backend.client import create_spx_client
from spx_mcp.config import SpxMcpConfig
from spx_mcp.errors import ProductKeyConfigError


def test_create_spx_client_reports_placeholder_key_details() -> None:
    config = SpxMcpConfig(
        repo_root=Path(".").resolve(),
        spx_base_url="http://localhost:8000",
        product_key=None,
        product_key_status="placeholder",
        product_key_search_details=(
            "process env SPX_PRODUCT_KEY=not set",
            "workspace .env (/tmp/workspace/.env)=placeholder REPLACE_ME",
        ),
        workspace_kind="managed",
        default_work_mode="runtime_mcp",
    )

    with pytest.raises(ProductKeyConfigError) as exc_info:
        create_spx_client(config)

    exc = exc_info.value
    assert "SPX_PRODUCT_KEY is missing or invalid for this MCP workspace." in str(exc)
    assert "workspace .env (/tmp/workspace/.env)=placeholder REPLACE_ME" in str(exc)
    assert exc.details["status"] == "placeholder"
    assert exc.details["workspace_kind"] == "managed"
