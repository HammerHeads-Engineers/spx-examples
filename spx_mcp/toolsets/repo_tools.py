# SPDX-License-Identifier: MIT
"""Repository-aware MCP tools."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from spx_mcp.backend.models import validate_catalog_model
from spx_mcp.errors import exception_to_response, success_response


REPO_TOOL_SPECS: List[Dict[str, Any]] = [
    {
        "name": "repo_list_packs",
        "description": "List industry packs defined in the repository catalog.",
        "write": False,
    },
    {
        "name": "repo_list_profiles",
        "description": "List quickstart profiles, optionally scoped to one pack.",
        "write": False,
    },
    {
        "name": "repo_find_models",
        "description": "Search catalog models by query, pack, profile, or protocol.",
        "write": False,
    },
    {
        "name": "repo_get_model",
        "description": "Return metadata for one catalog model id.",
        "write": False,
    },
    {
        "name": "repo_validate_model",
        "description": "Validate one catalog model with the repo's lightweight validator.",
        "write": False,
    },
]


def register_repo_tools(server, runtime) -> None:
    """Register tools that inspect repository metadata."""

    @server.tool(
        name="repo_list_packs",
        description="List industry packs defined in the repository catalog.",
    )
    def repo_list_packs() -> Dict[str, Any]:
        try:
            return success_response(packs=runtime.catalog.list_packs())
        except Exception as exc:
            return exception_to_response(exc)

    @server.tool(
        name="repo_list_profiles",
        description="List quickstart profiles, optionally scoped to one pack.",
    )
    def repo_list_profiles(pack_id: Optional[str] = None) -> Dict[str, Any]:
        try:
            return success_response(profiles=runtime.catalog.list_profiles(pack_id=pack_id))
        except Exception as exc:
            return exception_to_response(exc)

    @server.tool(
        name="repo_find_models",
        description="Search catalog models by query, pack, profile, or protocol.",
    )
    def repo_find_models(
        query: Optional[str] = None,
        pack_id: Optional[str] = None,
        profile_id: Optional[str] = None,
        protocol: Optional[str] = None,
    ) -> Dict[str, Any]:
        try:
            return success_response(
                models=runtime.catalog.find_models(
                    query=query,
                    pack_id=pack_id,
                    profile_id=profile_id,
                    protocol=protocol,
                )
            )
        except Exception as exc:
            return exception_to_response(exc)

    @server.tool(
        name="repo_get_model",
        description="Return metadata for one catalog model id.",
    )
    def repo_get_model(model_id: str) -> Dict[str, Any]:
        try:
            return success_response(model=runtime.catalog.get_model(model_id))
        except Exception as exc:
            return exception_to_response(exc)

    @server.tool(
        name="repo_validate_model",
        description="Validate one catalog model with the repo's lightweight validator.",
    )
    def repo_validate_model(model_id: str) -> Dict[str, Any]:
        try:
            return success_response(
                validation=validate_catalog_model(runtime.catalog, model_id)
            )
        except Exception as exc:
            return exception_to_response(exc)
