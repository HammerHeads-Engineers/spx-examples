# SPDX-License-Identifier: MIT
"""Diagnostics-oriented MCP tools for model validation and runtime inspection."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from spx_mcp.backend.diagnostics import (
    collect_logs,
    diagnose_instance,
    get_bindings,
    get_communication,
)
from spx_mcp.errors import exception_to_response, success_response


DIAGNOSTICS_TOOL_SPECS: List[Dict[str, Any]] = [
    {"name": "server_get_logs", "description": "Read runtime logs from an instance.", "write": False},
    {"name": "server_get_communication", "description": "Inspect an instance communication subtree.", "write": False},
    {"name": "server_get_bindings", "description": "Inspect protocol bindings for an instance.", "write": False},
    {"name": "server_diagnose_instance", "description": "Return a diagnostic snapshot of one instance.", "write": False},
]


def register_diagnostics_tools(server, runtime) -> None:
    """Register diagnostics and observability tools."""

    @server.tool(
        name="server_get_logs",
        description="Read runtime logs from an instance, with fallbacks for log nodes and log attributes.",
    )
    def server_get_logs(
        instance_key: str,
        attr_path: Optional[str] = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        try:
            client = runtime.create_client()
            return success_response(
                logs=collect_logs(client, instance_key, attr_path=attr_path, limit=limit)
            )
        except Exception as exc:
            return exception_to_response(exc)

    @server.tool(
        name="server_get_communication",
        description="Inspect an instance communication subtree or one specific protocol block.",
    )
    def server_get_communication(
        instance_key: str,
        protocol: Optional[str] = None,
    ) -> Dict[str, Any]:
        try:
            client = runtime.create_client()
            return success_response(
                communication=get_communication(client, instance_key, protocol=protocol)
            )
        except Exception as exc:
            return exception_to_response(exc)

    @server.tool(
        name="server_get_bindings",
        description="Inspect protocol bindings for an instance.",
    )
    def server_get_bindings(instance_key: str, protocol: str) -> Dict[str, Any]:
        try:
            client = runtime.create_client()
            return success_response(
                bindings=get_bindings(client, instance_key, protocol=protocol)
            )
        except Exception as exc:
            return exception_to_response(exc)

    @server.tool(
        name="server_diagnose_instance",
        description="Return instance state, model id, logs, communication, and optional bindings in one payload.",
    )
    def server_diagnose_instance(
        instance_key: str,
        log_attr_path: Optional[str] = None,
        protocol: Optional[str] = None,
    ) -> Dict[str, Any]:
        try:
            client = runtime.create_client()
            return success_response(
                diagnosis=diagnose_instance(
                    client,
                    instance_key,
                    log_attr_path=log_attr_path,
                    protocol=protocol,
                )
            )
        except Exception as exc:
            return exception_to_response(exc)
