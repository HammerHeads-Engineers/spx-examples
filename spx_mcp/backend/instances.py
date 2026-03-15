# SPDX-License-Identifier: MIT
"""SPX instance and tree inspection helpers."""

from __future__ import annotations

from typing import Any, Dict, List

from spx_mcp.backend.client import read_path


def list_registry_children(client, registry_name: str) -> List[str]:
    """Return child names for a top-level SPX registry such as models or instances."""
    registry = client[registry_name]
    try:
        return list(registry.keys())
    except Exception:
        doc = registry.get()
        return [
            child.get("name")
            for child in doc.get("children", [])
            if isinstance(child, dict) and child.get("name")
        ]


def get_instance_doc(client, instance_key: str) -> Dict[str, Any]:
    """Return the current JSON document for an instance."""
    return client["instances"][instance_key].get()


def get_attribute_value(instance, attr_path: str) -> Any:
    """Resolve an attribute path against an instance and return its internal value."""
    target = instance
    segments = [segment for segment in str(attr_path or "").strip("/").split("/") if segment]
    if not segments:
        raise ValueError("attr_path must contain at least one segment")
    for segment in segments:
        target = target[segment]
    value = getattr(target, "internal_value", target)
    if isinstance(value, dict) and "value" in value:
        return value["value"]
    return value


def read_instance_node(client, instance_key: str, relative_path: str) -> Any:
    """Resolve a path relative to an instance key."""
    return read_path(client, f"instances/{instance_key}/{relative_path}")
