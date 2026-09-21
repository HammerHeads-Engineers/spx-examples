# SPDX-License-Identifier: MIT
"""Diagnostics helpers for model validation, runtime logs, and protocol bindings."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from spx_mcp.backend.client import read_path
from spx_mcp.backend.instances import get_attribute_value, get_instance_doc


def collect_logs(
    client,
    instance_key: str,
    *,
    attr_path: Optional[str] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    """Read runtime logs from an instance using common log locations."""
    instance = client["instances"][instance_key]
    candidates: List[Tuple[str, str]] = []
    if attr_path:
        candidates.append(("attribute", attr_path))
    candidates.extend(
        [
            ("node", "logs"),
            ("attribute", "attributes/logs"),
            ("attribute", "attributes/_test_logs"),
        ]
    )

    checked: List[str] = []
    for kind, candidate in candidates:
        checked.append(candidate)
        try:
            if kind == "node":
                payload = read_path(client, f"instances/{instance_key}/{candidate}")
            else:
                payload = get_attribute_value(instance, candidate)
        except Exception:
            continue

        if isinstance(payload, list):
            return {
                "instance_key": instance_key,
                "source": candidate,
                "entries": payload[-max(0, limit):] if limit > 0 else payload,
                "checked": checked,
            }

        return {
            "instance_key": instance_key,
            "source": candidate,
            "entries": payload,
            "checked": checked,
        }

    return {
        "instance_key": instance_key,
        "source": None,
        "entries": [],
        "checked": checked,
    }


def get_communication(
    client,
    instance_key: str,
    *,
    protocol: Optional[str] = None,
) -> Dict[str, Any]:
    """Return communication data for an instance or one specific protocol block."""
    relative_path = "communication"
    if protocol:
        relative_path = f"{relative_path}/{protocol}"
    payload = read_path(client, f"instances/{instance_key}/{relative_path}")
    return {
        "instance_key": instance_key,
        "protocol": protocol,
        "path": relative_path,
        "payload": payload,
    }


def get_bindings(
    client,
    instance_key: str,
    *,
    protocol: str,
) -> Dict[str, Any]:
    """Return bindings for a specific communication protocol."""
    relative_path = f"communication/{protocol}/bindings"
    payload = read_path(client, f"instances/{instance_key}/{relative_path}")
    return {
        "instance_key": instance_key,
        "protocol": protocol,
        "path": relative_path,
        "payload": payload,
    }


def diagnose_instance(
    client,
    instance_key: str,
    *,
    log_attr_path: Optional[str] = None,
    protocol: Optional[str] = None,
) -> Dict[str, Any]:
    """Return a diagnostic snapshot for an instance."""
    instance_doc = get_instance_doc(client, instance_key)
    logs = collect_logs(client, instance_key, attr_path=log_attr_path)
    communication = _safe_communication_block(
        client,
        instance_key,
        protocol=protocol,
    )
    bindings = None
    if protocol:
        try:
            bindings = get_bindings(client, instance_key, protocol=protocol)
        except Exception as exc:
            bindings = {
                "instance_key": instance_key,
                "protocol": protocol,
                "path": f"communication/{protocol}/bindings",
                "payload": None,
                "error": str(exc),
            }

    return {
        "instance_key": instance_key,
        "state": _extract_state(instance_doc),
        "model_id": _extract_model_id(instance_doc),
        "instance": instance_doc,
        "logs": logs,
        "communication": communication,
        "bindings": bindings,
    }


def _extract_state(instance_doc: Dict[str, Any]) -> Optional[str]:
    state = instance_doc.get("state")
    if isinstance(state, str):
        return state
    attr = instance_doc.get("attr")
    if isinstance(attr, dict):
        state_attr = attr.get("state")
        if isinstance(state_attr, dict):
            value = state_attr.get("value")
            if isinstance(value, str):
                return value
    return None


def _extract_model_id(instance_doc: Dict[str, Any]) -> Optional[str]:
    for key in ("model_id", "model", "modelId"):
        value = instance_doc.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _safe_communication_block(
    client,
    instance_key: str,
    *,
    protocol: Optional[str],
) -> Dict[str, Any]:
    try:
        return get_communication(client, instance_key, protocol=protocol)
    except Exception as exc:
        path = "communication"
        if protocol:
            path = f"{path}/{protocol}"
        return {
            "instance_key": instance_key,
            "protocol": protocol,
            "path": path,
            "payload": None,
            "error": str(exc),
        }
