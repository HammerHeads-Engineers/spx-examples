# SPDX-License-Identifier: MIT
"""Write-enabled repository mutation tools."""

from __future__ import annotations

from typing import Any, Dict, List

from spx_mcp.backend.models import (
    delete_model_scenario,
    upsert_model_scenario,
)
from spx_mcp.errors import exception_to_response, success_response


REPO_WRITE_TOOL_SPECS: List[Dict[str, Any]] = [
    {
        "name": "repo_upsert_model_scenario",
        "description": "Create or replace one scenario definition in a catalog model YAML file.",
        "write": True,
    },
    {
        "name": "repo_delete_model_scenario",
        "description": "Delete one scenario definition from a catalog model YAML file.",
        "write": True,
    },
]


def register_repo_write_tools(server, runtime) -> None:
    """Register repo mutation tools guarded by runtime.allow_write."""

    @server.tool(
        name="repo_upsert_model_scenario",
        description="Create or replace one scenario definition in a catalog model YAML file.",
    )
    def repo_upsert_model_scenario(
        model_id: str,
        scenario_name: str,
        scenario: Dict[str, Any],
        replace: bool = True,
    ) -> Dict[str, Any]:
        try:
            runtime.require_write()
            return success_response(
                **upsert_model_scenario(
                    runtime.catalog,
                    model_id,
                    scenario_name,
                    scenario,
                    replace=replace,
                )
            )
        except Exception as exc:
            return exception_to_response(exc)

    @server.tool(
        name="repo_delete_model_scenario",
        description="Delete one scenario definition from a catalog model YAML file.",
    )
    def repo_delete_model_scenario(model_id: str, scenario_name: str) -> Dict[str, Any]:
        try:
            runtime.require_write()
            return success_response(
                **delete_model_scenario(
                    runtime.catalog,
                    model_id,
                    scenario_name,
                )
            )
        except Exception as exc:
            return exception_to_response(exc)
