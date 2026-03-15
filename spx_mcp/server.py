# SPDX-License-Identifier: MIT
"""FastMCP server construction for the local SPX MCP tool."""

from __future__ import annotations

from importlib.util import find_spec

from .config import python_supports_mcp, runtime_requirement_message


def build_server(config):
    """Create and configure the FastMCP server instance."""
    FastMCP = _import_fastmcp()
    SpxMcpRuntime, register_all_tools = _import_runtime_components()
    runtime = SpxMcpRuntime(config)
    server = FastMCP(
        name="spx-examples",
        instructions=(
            "Local MCP tools for the spx-examples repository. "
            "Use read-only inspection by default; write tools are exposed only when "
            "the server is started with --allow-write."
        ),
        dependencies=["spx-python"],
    )
    register_all_tools(server, runtime)
    return server


def _import_fastmcp():
    if not python_supports_mcp():
        raise RuntimeError(runtime_requirement_message())
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:  # pragma: no cover - depends on optional runtime
        raise RuntimeError(runtime_requirement_message()) from exc
    return FastMCP


def _import_runtime_components():
    if find_spec("spx_python") is None:
        raise RuntimeError(
            "The local MCP tool requires the 'spx-python' package. "
            "Install project dependencies with 'poetry install --with dev'."
        )
    try:
        from .runtime import SpxMcpRuntime
        from .toolsets import register_all_tools
    except ImportError as exc:  # pragma: no cover - depends on optional runtime
        raise RuntimeError(
            "The local MCP tool could not import its runtime dependencies. "
            "Install project dependencies with 'poetry install --with dev'."
        ) from exc
    return SpxMcpRuntime, register_all_tools
