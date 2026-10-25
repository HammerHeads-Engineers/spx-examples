# SPDX-License-Identifier: MIT
"""SPX connection helpers for runtime MCP tools."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from spx_mcp.backend.instances import list_registry_children


def list_connections(client) -> List[str]:
    """Return connection names present on the running SPX server."""
    return list_registry_children(client, "connections")


def get_connection_doc(client, connection_name: str) -> Dict[str, Any]:
    """Return the current JSON document for one runtime connection."""
    normalized_name = normalize_connection_name(connection_name)
    return client["connections"][normalized_name].get()


def upsert_connection(
    client,
    connection_name: str,
    *,
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
    """Create or replace a runtime connection."""
    normalized_name = normalize_connection_name(connection_name)
    definition = build_connection_definition(
        from_expr=from_expr,
        to_expr=to_expr,
        source_instance_key=source_instance_key,
        source_attr_path=source_attr_path,
        target_instance_key=target_instance_key,
        target_attr_path=target_attr_path,
    )

    connections = client["connections"]
    existed = normalized_name in list_connections(client)
    if existed and not replace:
        raise ValueError(f"Connection '{normalized_name}' already exists")

    stop_result = None
    if existed:
        existing = connections[normalized_name]
        if stop_existing:
            stop_result = invoke_optional(existing, "stop")
        del connections[normalized_name]

    connections[normalized_name] = definition
    connection = connections[normalized_name]
    start_result = None
    if start:
        start_result = invoke_required(connection, "start")

    return {
        "connection_name": normalized_name,
        "definition": definition,
        "replaced": existed,
        "stopped_existing": bool(existed and stop_existing),
        "stop_result": stop_result,
        "started": start,
        "start_result": start_result,
        "connection": connection.get(),
    }


def delete_connection(
    client,
    connection_name: str,
    *,
    stop_if_running: bool = True,
) -> Dict[str, Any]:
    """Delete one runtime connection."""
    normalized_name = normalize_connection_name(connection_name)
    connections = client["connections"]
    connection = connections[normalized_name]
    stop_result = None
    if stop_if_running:
        stop_result = invoke_optional(connection, "stop")
    del connections[normalized_name]
    return {
        "connection_name": normalized_name,
        "deleted": True,
        "stopped": bool(stop_if_running),
        "stop_result": stop_result,
    }


def start_connections(client) -> Dict[str, Any]:
    """Start the global SPX connections container."""
    return {"result": invoke_required(client["connections"], "start")}


def stop_connections(client) -> Dict[str, Any]:
    """Stop the global SPX connections container."""
    return {"result": invoke_required(client["connections"], "stop")}


def start_connection(client, connection_name: str) -> Dict[str, Any]:
    """Start one runtime connection."""
    connection = client["connections"][normalize_connection_name(connection_name)]
    return {
        "connection_name": normalize_connection_name(connection_name),
        "result": invoke_required(connection, "start"),
        "connection": connection.get(),
    }


def stop_connection(client, connection_name: str) -> Dict[str, Any]:
    """Stop one runtime connection."""
    connection = client["connections"][normalize_connection_name(connection_name)]
    return {
        "connection_name": normalize_connection_name(connection_name),
        "result": invoke_required(connection, "stop"),
        "connection": connection.get(),
    }


def run_connection(client, connection_name: str) -> Dict[str, Any]:
    """Run one runtime connection once."""
    connection = client["connections"][normalize_connection_name(connection_name)]
    return {
        "connection_name": normalize_connection_name(connection_name),
        "result": invoke_required(connection, "run"),
        "connection": connection.get(),
    }


def build_connection_definition(
    *,
    from_expr: Optional[str] = None,
    to_expr: Optional[str] = None,
    source_instance_key: Optional[str] = None,
    source_attr_path: Optional[str] = None,
    target_instance_key: Optional[str] = None,
    target_attr_path: Optional[str] = None,
) -> Dict[str, str]:
    """Build an SPX connection definition from expressions or endpoint parts."""
    resolved_from = normalize_expr(from_expr, label="from_expr")
    resolved_to = normalize_expr(to_expr, label="to_expr")

    if resolved_from is None:
        resolved_from = build_endpoint_expr(
            "$out",
            instance_key=source_instance_key,
            attr_path=source_attr_path,
            instance_label="source_instance_key",
            attr_label="source_attr_path",
        )
    if resolved_to is None:
        resolved_to = build_endpoint_expr(
            "$in",
            instance_key=target_instance_key,
            attr_path=target_attr_path,
            instance_label="target_instance_key",
            attr_label="target_attr_path",
        )
    return {"from": resolved_from, "to": resolved_to}


def build_endpoint_expr(
    function_name: str,
    *,
    instance_key: Optional[str],
    attr_path: Optional[str],
    instance_label: str,
    attr_label: str,
) -> str:
    """Build an SPX endpoint expression such as $out(instance.attr)."""
    normalized_instance = normalize_required(instance_key, instance_label)
    normalized_attr = normalize_attr_endpoint(attr_path, attr_label)
    return f"{function_name}({normalized_instance}.{normalized_attr})"


def normalize_connection_name(connection_name: str) -> str:
    """Validate and normalize a runtime connection name."""
    return normalize_required(connection_name, "connection_name")


def normalize_expr(value: Optional[str], *, label: str) -> Optional[str]:
    """Normalize an optional SPX expression."""
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{label} must not be empty")
    return normalized


def normalize_required(value: Optional[str], label: str) -> str:
    """Normalize a required string argument."""
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{label} is required")
    return normalized


def normalize_attr_endpoint(attr_path: Optional[str], label: str) -> str:
    """Normalize common MCP attribute paths to SPX connection endpoints."""
    normalized = normalize_required(attr_path, label).strip("/")
    parts = [part for part in normalized.split("/") if part]
    if not parts:
        raise ValueError(f"{label} is required")
    if parts[0] == "attributes":
        parts = parts[1:]
    if parts and parts[-1] in {"internal_value", "external_value", "value"}:
        parts = parts[:-1]
    if len(parts) != 1:
        raise ValueError(
            f"{label} must identify a single attribute, got '{attr_path}'"
        )
    return parts[0]


def invoke_required(node, method_name: str):
    """Invoke a required runtime method on a SPX node."""
    method = getattr(node, method_name, None)
    if not callable(method):
        raise AttributeError(f"Runtime node does not support method '{method_name}'")
    return method()


def invoke_optional(node, method_name: str):
    """Invoke an optional runtime method on a SPX node."""
    method = getattr(node, method_name, None)
    if callable(method):
        return method()
    return None
