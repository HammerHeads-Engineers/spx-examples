# SPDX-License-Identifier: MIT
"""Write-enabled SPX MCP tools."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from spx_mcp.backend.bootstrap import (
    bootstrap_pack,
    bootstrap_profile,
    ensure_instance,
    register_model_and_ensure_instance,
    summarize_runtime_instance,
)
from spx_mcp.backend.instances import (
    delete_instance_scenario,
    ramp_attribute_value,
    start_instance_scenario,
    set_attribute_value,
    set_attribute_values,
    stop_instance_scenario,
    upsert_instance_scenario,
)
from spx_mcp.backend.models import register_model_from_catalog
from spx_mcp.errors import exception_to_response, success_response


SERVER_WRITE_TOOL_SPECS: List[Dict[str, Any]] = [
    {"name": "server_register_model_from_catalog", "description": "Validate and register one model from the repo catalog.", "write": True},
    {"name": "server_register_model_and_ensure_instance", "description": "Minimal runtime flow: register one catalog model, ensure one instance exists, and stop once it is RUNNING.", "write": True},
    {"name": "server_ensure_instance", "description": "Ensure an instance exists, creating it from the given model if needed, and return its minimal runtime summary.", "write": True},
    {"name": "server_start_instance", "description": "Start one instance.", "write": True},
    {"name": "server_stop_instance", "description": "Stop one instance.", "write": True},
    {"name": "server_reset_instance", "description": "Reset one instance.", "write": True},
    {"name": "server_set_attr", "description": "Set one instance attribute by path.", "write": True},
    {"name": "server_set_attrs", "description": "Set multiple instance attributes by path.", "write": True},
    {"name": "server_ramp_attr", "description": "Ramp one numeric instance attribute over time.", "write": True},
    {"name": "server_upsert_scenario", "description": "Create or replace one runtime scenario on an instance.", "write": True},
    {"name": "server_start_scenario", "description": "Start one runtime scenario on an instance.", "write": True},
    {"name": "server_stop_scenario", "description": "Stop one runtime scenario on an instance.", "write": True},
    {"name": "server_delete_scenario", "description": "Delete one runtime scenario from an instance.", "write": True},
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
        name="server_register_model_and_ensure_instance",
        description="Minimal runtime flow: register one catalog model, ensure one instance exists, and stop once it is RUNNING.",
    )
    def server_register_model_and_ensure_instance(
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
            return success_response(
                **register_model_and_ensure_instance(
                    client,
                    runtime.catalog,
                    model_id=model_id,
                    instance_key=instance_key,
                    start=start,
                    recreate=recreate,
                    overrides=overrides,
                    meta_parameters=meta_parameters,
                )
            )
        except Exception as exc:
            return exception_to_response(exc)

    @server.tool(
        name="server_ensure_instance",
        description="Ensure an instance exists, creating it from the given model if needed, and return its minimal runtime summary.",
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
                **summarize_runtime_instance(
                    instance,
                    model_id=model_id,
                    instance_key=instance_key,
                )
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
            resolved_path = set_attribute_value(instance, attr_path, value)
            return success_response(
                instance_key=instance_key,
                attr_path=attr_path,
                resolved_path=resolved_path,
                value=value,
            )
        except Exception as exc:
            return exception_to_response(exc)

    @server.tool(
        name="server_set_attrs",
        description="Set multiple instance attributes by path.",
    )
    def server_set_attrs(instance_key: str, values: Dict[str, Any]) -> Dict[str, Any]:
        try:
            runtime.require_write()
            client = runtime.create_client()
            instance = client["instances"][instance_key]
            resolved_paths = set_attribute_values(instance, values)
            return success_response(
                instance_key=instance_key,
                values=values,
                resolved_paths=resolved_paths,
            )
        except Exception as exc:
            return exception_to_response(exc)

    @server.tool(
        name="server_ramp_attr",
        description="Ramp one numeric instance attribute over time.",
    )
    def server_ramp_attr(
        instance_key: str,
        attr_path: str,
        target: Any,
        duration_s: float,
        steps: int = 10,
        start_value: Any = None,
    ) -> Dict[str, Any]:
        try:
            runtime.require_write()
            client = runtime.create_client()
            instance = client["instances"][instance_key]
            result = ramp_attribute_value(
                instance,
                attr_path,
                target,
                duration_s=duration_s,
                steps=steps,
                start_value=start_value,
            )
            return success_response(instance_key=instance_key, **result)
        except Exception as exc:
            return exception_to_response(exc)

    @server.tool(
        name="server_upsert_scenario",
        description="Create or replace one runtime scenario on an instance.",
    )
    def server_upsert_scenario(
        instance_key: str,
        scenario_name: str,
        scenario: Dict[str, Any],
        replace: bool = True,
        start: bool = False,
        stop_existing: bool = True,
    ) -> Dict[str, Any]:
        try:
            runtime.require_write()
            client = runtime.create_client()
            instance = client["instances"][instance_key]
            result = upsert_instance_scenario(
                instance,
                scenario_name,
                scenario,
                replace=replace,
                start=start,
                stop_existing=stop_existing,
            )
            return success_response(instance_key=instance_key, **result)
        except Exception as exc:
            return exception_to_response(exc)

    @server.tool(
        name="server_start_scenario",
        description="Start one runtime scenario on an instance.",
    )
    def server_start_scenario(instance_key: str, scenario_name: str) -> Dict[str, Any]:
        try:
            runtime.require_write()
            client = runtime.create_client()
            instance = client["instances"][instance_key]
            return success_response(
                instance_key=instance_key,
                **start_instance_scenario(instance, scenario_name),
            )
        except Exception as exc:
            return exception_to_response(exc)

    @server.tool(
        name="server_stop_scenario",
        description="Stop one runtime scenario on an instance.",
    )
    def server_stop_scenario(instance_key: str, scenario_name: str) -> Dict[str, Any]:
        try:
            runtime.require_write()
            client = runtime.create_client()
            instance = client["instances"][instance_key]
            return success_response(
                instance_key=instance_key,
                **stop_instance_scenario(instance, scenario_name),
            )
        except Exception as exc:
            return exception_to_response(exc)

    @server.tool(
        name="server_delete_scenario",
        description="Delete one runtime scenario from an instance.",
    )
    def server_delete_scenario(
        instance_key: str,
        scenario_name: str,
        stop_if_running: bool = True,
    ) -> Dict[str, Any]:
        try:
            runtime.require_write()
            client = runtime.create_client()
            instance = client["instances"][instance_key]
            return success_response(
                instance_key=instance_key,
                **delete_instance_scenario(
                    instance,
                    scenario_name,
                    stop_if_running=stop_if_running,
                ),
            )
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
