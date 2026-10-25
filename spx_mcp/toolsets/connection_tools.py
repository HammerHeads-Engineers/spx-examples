# SPDX-License-Identifier: MIT
"""SPX runtime connection MCP tools."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from spx_mcp.backend.connections import (
    delete_connection,
    get_connection_doc,
    list_connections,
    run_connection,
    start_connection,
    start_connections,
    stop_connection,
    stop_connections,
    upsert_connection,
)
from spx_mcp.errors import exception_to_response, success_response


CONNECTION_READ_TOOL_SPECS: List[Dict[str, Any]] = [
    {"name": "server_list_connections", "description": "List runtime connection names present on the running SPX server.", "write": False},
    {"name": "server_get_connection", "description": "Return the current JSON document for one runtime connection.", "write": False},
]

CONNECTION_WRITE_TOOL_SPECS: List[Dict[str, Any]] = [
    {"name": "server_upsert_connection", "description": "Create or replace one runtime connection between SPX instance attributes.", "write": True},
    {"name": "server_delete_connection", "description": "Delete one runtime connection.", "write": True},
    {"name": "server_start_connections", "description": "Start the global SPX connections container.", "write": True},
    {"name": "server_stop_connections", "description": "Stop the global SPX connections container.", "write": True},
    {"name": "server_start_connection", "description": "Start one runtime connection.", "write": True},
    {"name": "server_stop_connection", "description": "Stop one runtime connection.", "write": True},
    {"name": "server_run_connection", "description": "Run one runtime connection once.", "write": True},
]


def register_connection_read_tools(server, runtime) -> None:
    """Register read-only runtime connection tools."""

    @server.tool(
        name="server_list_connections",
        description="List runtime connection names present on the running SPX server.",
    )
    def server_list_connections() -> Dict[str, Any]:
        try:
            client = runtime.create_client()
            return success_response(connections=list_connections(client))
        except Exception as exc:
            return exception_to_response(exc)

    @server.tool(
        name="server_get_connection",
        description="Return the current JSON document for one runtime connection.",
    )
    def server_get_connection(connection_name: str) -> Dict[str, Any]:
        try:
            client = runtime.create_client()
            return success_response(
                connection_name=connection_name,
                connection=get_connection_doc(client, connection_name),
            )
        except Exception as exc:
            return exception_to_response(exc)


def register_connection_write_tools(server, runtime) -> None:
    """Register write-enabled runtime connection tools."""

    @server.tool(
        name="server_upsert_connection",
        description="Create or replace one runtime connection between SPX instance attributes.",
    )
    def server_upsert_connection(
        connection_name: str,
        from_expr: Optional[str] = None,
        to_expr: Optional[str] = None,
        source_instance_key: Optional[str] = None,
        source_attr_path: Optional[str] = None,
        target_instance_key: Optional[str] = None,
        target_attr_path: Optional[str] = None,
        replace: bool = True,
        start: bool = False,
        stop_existing: bool = True,
    ) -> Dict[str, Any]:
        try:
            runtime.require_write()
            client = runtime.create_client()
            return success_response(
                **upsert_connection(
                    client,
                    connection_name,
                    from_expr=from_expr,
                    to_expr=to_expr,
                    source_instance_key=source_instance_key,
                    source_attr_path=source_attr_path,
                    target_instance_key=target_instance_key,
                    target_attr_path=target_attr_path,
                    replace=replace,
                    start=start,
                    stop_existing=stop_existing,
                )
            )
        except Exception as exc:
            return exception_to_response(exc)

    @server.tool(
        name="server_delete_connection",
        description="Delete one runtime connection.",
    )
    def server_delete_connection(
        connection_name: str,
        stop_if_running: bool = True,
    ) -> Dict[str, Any]:
        try:
            runtime.require_write()
            client = runtime.create_client()
            return success_response(
                **delete_connection(
                    client,
                    connection_name,
                    stop_if_running=stop_if_running,
                )
            )
        except Exception as exc:
            return exception_to_response(exc)

    @server.tool(
        name="server_start_connections",
        description="Start the global SPX connections container.",
    )
    def server_start_connections() -> Dict[str, Any]:
        try:
            runtime.require_write()
            client = runtime.create_client()
            return success_response(**start_connections(client))
        except Exception as exc:
            return exception_to_response(exc)

    @server.tool(
        name="server_stop_connections",
        description="Stop the global SPX connections container.",
    )
    def server_stop_connections() -> Dict[str, Any]:
        try:
            runtime.require_write()
            client = runtime.create_client()
            return success_response(**stop_connections(client))
        except Exception as exc:
            return exception_to_response(exc)

    @server.tool(
        name="server_start_connection",
        description="Start one runtime connection.",
    )
    def server_start_connection(connection_name: str) -> Dict[str, Any]:
        try:
            runtime.require_write()
            client = runtime.create_client()
            return success_response(**start_connection(client, connection_name))
        except Exception as exc:
            return exception_to_response(exc)

    @server.tool(
        name="server_stop_connection",
        description="Stop one runtime connection.",
    )
    def server_stop_connection(connection_name: str) -> Dict[str, Any]:
        try:
            runtime.require_write()
            client = runtime.create_client()
            return success_response(**stop_connection(client, connection_name))
        except Exception as exc:
            return exception_to_response(exc)

    @server.tool(
        name="server_run_connection",
        description="Run one runtime connection once.",
    )
    def server_run_connection(connection_name: str) -> Dict[str, Any]:
        try:
            runtime.require_write()
            client = runtime.create_client()
            return success_response(**run_connection(client, connection_name))
        except Exception as exc:
            return exception_to_response(exc)
