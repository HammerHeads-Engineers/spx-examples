# SPDX-License-Identifier: MIT
"""SPX client helpers built on top of spx_python."""

from __future__ import annotations

from typing import Any

import spx_python
from spx_python.client import SpxClient

from spx_mcp.config import SpxMcpConfig
from spx_mcp.errors import ProductKeyConfigError


def create_spx_client(config: SpxMcpConfig) -> SpxClient:
    """Instantiate an SPX client using the current MCP configuration."""
    if not config.has_valid_product_key:
        raise ProductKeyConfigError(
            config.product_key_error_message(),
            details=config.product_key_error_details(),
        )
    return spx_python.init(
        address=config.spx_base_url,
        product_key=config.product_key,
        pretty_errors=config.pretty_errors,
        client_fault_verbose=config.fault_verbose,
    )


def resolve_node_value(node: Any) -> Any:
    """Return the JSON/value payload for a client node or plain Python object."""
    if isinstance(node, SpxClient):
        return node.get()
    return node


def read_path(client: SpxClient, path: str) -> Any:
    """Resolve a slash-separated path against the SPX client tree."""
    segments = [segment for segment in str(path or "").strip("/").split("/") if segment]
    if not segments:
        return client.get()
    target: Any = client
    for segment in segments:
        target = target[segment]
    return resolve_node_value(target)
