# SPDX-License-Identifier: MIT
"""Tool registration and static metadata for the SPX MCP server."""

from __future__ import annotations

from typing import Any, Dict, List


def get_tool_specs(*, allow_write: bool) -> List[Dict[str, Any]]:
    """Return a static list of tool metadata for CLI listing and docs."""
    from .connection_tools import (
        CONNECTION_READ_TOOL_SPECS,
        CONNECTION_WRITE_TOOL_SPECS,
    )
    from .diagnostics_tools import DIAGNOSTICS_TOOL_SPECS
    from .repo_write_tools import REPO_WRITE_TOOL_SPECS
    from .repo_tools import REPO_TOOL_SPECS
    from .server_read_tools import SERVER_READ_TOOL_SPECS
    from .server_write_tools import SERVER_WRITE_TOOL_SPECS

    specs: List[Dict[str, Any]] = []
    specs.extend(REPO_TOOL_SPECS)
    specs.extend(SERVER_READ_TOOL_SPECS)
    specs.extend(CONNECTION_READ_TOOL_SPECS)
    specs.extend(DIAGNOSTICS_TOOL_SPECS)
    if allow_write:
        specs.extend(REPO_WRITE_TOOL_SPECS)
        specs.extend(SERVER_WRITE_TOOL_SPECS)
        specs.extend(CONNECTION_WRITE_TOOL_SPECS)
    return specs


def register_all_tools(server, runtime) -> None:
    """Register all MCP tool groups for the current runtime."""
    from .connection_tools import (
        register_connection_read_tools,
        register_connection_write_tools,
    )
    from .diagnostics_tools import register_diagnostics_tools
    from .repo_write_tools import register_repo_write_tools
    from .repo_tools import register_repo_tools
    from .server_read_tools import register_server_read_tools
    from .server_write_tools import register_server_write_tools

    register_repo_tools(server, runtime)
    register_server_read_tools(server, runtime)
    register_connection_read_tools(server, runtime)
    register_diagnostics_tools(server, runtime)
    if runtime.config.allow_write:
        register_repo_write_tools(server, runtime)
        register_server_write_tools(server, runtime)
        register_connection_write_tools(server, runtime)
