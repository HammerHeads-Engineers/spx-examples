# SPDX-License-Identifier: MIT
"""Read-only SPX server inspection tools."""

from __future__ import annotations

from typing import Any, Dict, List

from spx_mcp.backend.client import read_path
from spx_mcp.backend.instances import (
    get_scenario_doc,
    get_attribute_value,
    get_attribute_values,
    get_instance_doc,
    list_instance_scenarios,
    list_registry_children,
    resolve_attribute_read_path,
)
from spx_mcp.errors import exception_to_response, success_response


SERVER_READ_TOOL_SPECS: List[Dict[str, Any]] = [
    {"name": "health", "description": "Verify connectivity to the configured SPX server.", "write": False},
    {"name": "server_list_models", "description": "List model ids present on the running SPX server.", "write": False},
    {"name": "server_list_instances", "description": "List instance keys present on the running SPX server.", "write": False},
    {"name": "server_get_instance", "description": "Return the current JSON document for one instance.", "write": False},
    {"name": "server_list_scenarios", "description": "List scenario names present on one running instance.", "write": False},
    {"name": "server_get_scenario", "description": "Return the current JSON document for one runtime scenario.", "write": False},
    {"name": "server_get_attr", "description": "Return one attribute value from an instance.", "write": False},
    {"name": "server_get_attrs", "description": "Return multiple attribute values from an instance.", "write": False},
    {"name": "server_get_node", "description": "Return any SPX tree node or leaf value by path.", "write": False},
]


def register_server_read_tools(server, runtime) -> None:
    """Register read-only tools backed by spx_python."""

    @server.tool(
        name="health",
        description="Verify connectivity to the configured SPX server.",
    )
    def health() -> Dict[str, Any]:
        try:
            client = runtime.create_client()
            root = client.get()
            return success_response(
                base_url=runtime.config.spx_base_url,
                reachable=True,
                root_kind=type(root).__name__,
            )
        except Exception as exc:
            return exception_to_response(exc)

    @server.tool(
        name="server_list_models",
        description="List model ids present on the running SPX server.",
    )
    def server_list_models() -> Dict[str, Any]:
        try:
            client = runtime.create_client()
            return success_response(models=list_registry_children(client, "models"))
        except Exception as exc:
            return exception_to_response(exc)

    @server.tool(
        name="server_list_instances",
        description="List instance keys present on the running SPX server.",
    )
    def server_list_instances() -> Dict[str, Any]:
        try:
            client = runtime.create_client()
            return success_response(instances=list_registry_children(client, "instances"))
        except Exception as exc:
            return exception_to_response(exc)

    @server.tool(
        name="server_get_instance",
        description="Return the current JSON document for one instance.",
    )
    def server_get_instance(instance_key: str) -> Dict[str, Any]:
        try:
            client = runtime.create_client()
            return success_response(instance=get_instance_doc(client, instance_key))
        except Exception as exc:
            return exception_to_response(exc)

    @server.tool(
        name="server_list_scenarios",
        description="List scenario names present on one running instance.",
    )
    def server_list_scenarios(instance_key: str) -> Dict[str, Any]:
        try:
            client = runtime.create_client()
            instance = client["instances"][instance_key]
            return success_response(
                instance_key=instance_key,
                scenarios=list_instance_scenarios(instance),
            )
        except Exception as exc:
            return exception_to_response(exc)

    @server.tool(
        name="server_get_scenario",
        description="Return the current JSON document for one runtime scenario.",
    )
    def server_get_scenario(instance_key: str, scenario_name: str) -> Dict[str, Any]:
        try:
            client = runtime.create_client()
            instance = client["instances"][instance_key]
            return success_response(
                instance_key=instance_key,
                scenario_name=scenario_name,
                scenario=get_scenario_doc(instance, scenario_name),
            )
        except Exception as exc:
            return exception_to_response(exc)

    @server.tool(
        name="server_get_attr",
        description="Return one attribute value from an instance.",
    )
    def server_get_attr(instance_key: str, attr_path: str) -> Dict[str, Any]:
        try:
            client = runtime.create_client()
            instance = client["instances"][instance_key]
            return success_response(
                instance_key=instance_key,
                attr_path=attr_path,
                resolved_path=resolve_attribute_read_path(attr_path),
                value=get_attribute_value(instance, attr_path),
            )
        except Exception as exc:
            return exception_to_response(exc)

    @server.tool(
        name="server_get_attrs",
        description="Return multiple attribute values from an instance.",
    )
    def server_get_attrs(instance_key: str, attr_paths: List[str]) -> Dict[str, Any]:
        try:
            client = runtime.create_client()
            instance = client["instances"][instance_key]
            return success_response(
                instance_key=instance_key,
                resolved_paths={
                    str(attr_path): resolve_attribute_read_path(str(attr_path))
                    for attr_path in attr_paths
                },
                values=get_attribute_values(instance, attr_paths),
            )
        except Exception as exc:
            return exception_to_response(exc)

    @server.tool(
        name="server_get_node",
        description="Return any SPX tree node or leaf value by slash-separated path.",
    )
    def server_get_node(path: str) -> Dict[str, Any]:
        try:
            client = runtime.create_client()
            return success_response(path=path, payload=read_path(client, path))
        except Exception as exc:
            return exception_to_response(exc)
