# SPDX-License-Identifier: MIT
"""Write-enabled SPX MCP tools."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from spx_mcp.backend.bootstrap import bootstrap_pack, bootstrap_profile, ensure_instance
from spx_mcp.backend.models import register_model_from_catalog
from spx_mcp.errors import exception_to_response, success_response


SERVER_WRITE_TOOL_SPECS: List[Dict[str, Any]] = [
    {"name": "server_register_model_from_catalog", "description": "Validate and register one model from the repo catalog.", "write": True},
    {"name": "server_ensure_instance", "description": "Ensure an instance exists, creating it from the given model if needed.", "write": True},
    {"name": "server_start_instance", "description": "Start one instance.", "write": True},
    {"name": "server_stop_instance", "description": "Stop one instance.", "write": True},
    {"name": "server_reset_instance", "description": "Reset one instance.", "write": True},
    {"name": "server_set_attr", "description": "Set one instance attribute by path.", "write": True},
    {"name": "repo_bootstrap_pack", "description": "Register a pack's models and create its default instances.", "write": True},
    {"name": "repo_bootstrap_profile", "description": "Register all models referenced by a quickstart profile.", "write": True},
]


def register_server_write_tools(server, runtime) -> None:
    """Register mutation tools guarded by runtime.allow_write."""

    @server.tool(
        name="server_register_model_from_catalog",
        description="Validate and register one model from the repo catalog.",
    )
    def server_register_model_from_catalog(model_id: str) -> Dict[str, Any]:
        try:
            runtime.require_write()
            client = runtime.create_client()
            return success_response(
                result=register_model_from_catalog(client, runtime.catalog, model_id)
            )
        except Exception as exc:
            return exception_to_response(exc)

    @server.tool(
        name="server_ensure_instance",
        description="Ensure an instance exists, creating it from the given model if needed.",
    )
    def server_ensure_instance(
        model_id: str,
        instance_key: str,
        start: bool = True,
        recreate: bool = False,
        overrides: Optional[Dict[str, Any]] = None,
        meta_parameters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        try:
            runtime.require_write()
            client = runtime.create_client()
            instance = ensure_instance(
                client,
                model_id=model_id,
                instance_key=instance_key,
                model_path=runtime.catalog.get_model_path(model_id),
                overrides=overrides,
                meta_parameters=meta_parameters,
                recreate=recreate,
                ensure_running=start,
                start_on_create=start,
            )
            return success_response(
                instance_key=instance_key,
                model_id=model_id,
                state=getattr(instance, "state", None),
            )
        except Exception as exc:
            return exception_to_response(exc)

    @server.tool(
        name="server_start_instance",
        description="Start one instance.",
    )
    def server_start_instance(instance_key: str) -> Dict[str, Any]:
        try:
            runtime.require_write()
            client = runtime.create_client()
            instance = client["instances"][instance_key]
            instance.start()
            return success_response(instance_key=instance_key, state=getattr(instance, "state", None))
        except Exception as exc:
            return exception_to_response(exc)

    @server.tool(
        name="server_stop_instance",
        description="Stop one instance.",
    )
    def server_stop_instance(instance_key: str) -> Dict[str, Any]:
        try:
            runtime.require_write()
            client = runtime.create_client()
            instance = client["instances"][instance_key]
            instance.stop()
            return success_response(instance_key=instance_key, state=getattr(instance, "state", None))
        except Exception as exc:
            return exception_to_response(exc)

    @server.tool(
        name="server_reset_instance",
        description="Reset one instance.",
    )
    def server_reset_instance(instance_key: str) -> Dict[str, Any]:
        try:
            runtime.require_write()
            client = runtime.create_client()
            instance = client["instances"][instance_key]
            instance.reset()
            return success_response(instance_key=instance_key, state=getattr(instance, "state", None))
        except Exception as exc:
            return exception_to_response(exc)

    @server.tool(
        name="server_set_attr",
        description="Set one instance attribute by path.",
    )
    def server_set_attr(instance_key: str, attr_path: str, value: Any) -> Dict[str, Any]:
        try:
            runtime.require_write()
            client = runtime.create_client()
            instance = client["instances"][instance_key]
            instance.put_attr(attr_path, value)
            return success_response(instance_key=instance_key, attr_path=attr_path, value=value)
        except Exception as exc:
            return exception_to_response(exc)

    @server.tool(
        name="repo_bootstrap_pack",
        description="Register a pack's models and create its default instances.",
    )
    def repo_bootstrap_pack(pack_id: str) -> Dict[str, Any]:
        try:
            runtime.require_write()
            client = runtime.create_client()
            return success_response(result=bootstrap_pack(client, runtime.catalog, pack_id))
        except Exception as exc:
            return exception_to_response(exc)

    @server.tool(
        name="repo_bootstrap_profile",
        description="Register all models referenced by a quickstart profile.",
    )
    def repo_bootstrap_profile(profile_id: str) -> Dict[str, Any]:
        try:
            runtime.require_write()
            client = runtime.create_client()
            return success_response(result=bootstrap_profile(client, runtime.catalog, profile_id))
        except Exception as exc:
            return exception_to_response(exc)
