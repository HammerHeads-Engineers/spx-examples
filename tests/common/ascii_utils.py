# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Hammerheads Engineers Sp. z o.o.
# See the accompanying LICENSE file for terms.

"""Helpers for resolving ASCII/SCPI connection details from SPX instance objects.

The ASCII protocol can auto-assign a port (starting from 5025) when not
explicitly configured. Integration tests should discover the effective port
from the running instance instead of hardcoding a single value.
"""

from __future__ import annotations

import time
from typing import Any, Optional


def _unwrap_value(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "internal_value"):
        return getattr(value, "internal_value")
    if isinstance(value, dict) and "value" in value:
        return value.get("value")
    if hasattr(value, "value"):
        return getattr(value, "value")
    return value


def _coerce_int(value: Any) -> Optional[int]:
    value = _unwrap_value(value)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _read_attr(obj: Any, name: str) -> Any:
    if obj is None:
        return None

    try:
        value = getattr(obj, name)
    except Exception:
        value = None

    # spx_python returns a callable method stub for unknown names; treat it as missing.
    if callable(value):
        value = None
    if value is not None:
        return value

    if isinstance(obj, dict):
        if name in obj:
            return obj.get(name)
        attr = obj.get("attr")
        if isinstance(attr, dict):
            entry = attr.get(name)
            if isinstance(entry, dict) and "value" in entry:
                return entry.get("value")
            if entry is not None:
                return entry

    try:
        attr = obj["attr"]
    except Exception:
        attr = None
    if isinstance(attr, dict):
        entry = attr.get(name)
        if isinstance(entry, dict) and "value" in entry:
            return entry.get("value")
        if entry is not None:
            return entry

    get_fn = getattr(obj, "get", None)
    if callable(get_fn):
        try:
            doc = get_fn()
        except Exception:
            doc = None
        if isinstance(doc, dict):
            if name in doc and not isinstance(doc.get(name), dict):
                return doc.get(name)
            attr = doc.get("attr")
            if isinstance(attr, dict):
                entry = attr.get(name)
                if isinstance(entry, dict) and "value" in entry:
                    return entry.get("value")
                if entry is not None:
                    return entry

    return None


def _get_communication_node(instance: Any, key: str) -> Any:
    try:
        comms = instance["communication"]
    except Exception:
        comms = instance.get("communication") if isinstance(instance, dict) else None
    if comms is None:
        return None

    if isinstance(comms, dict):
        if key in comms:
            return comms.get(key)
    if isinstance(comms, list):
        for entry in comms:
            if isinstance(entry, dict) and key in entry:
                return entry.get(key)

    try:
        return comms[key]
    except Exception:
        return None


def resolve_ascii_port(instance: Any, *, comm_key: str = "ascii") -> Optional[int]:
    comm = _get_communication_node(instance, comm_key)
    if comm is None:
        return None
    return _coerce_int(_read_attr(comm, "port"))


def wait_for_ascii_port(
    instance: Any,
    *,
    comm_key: str = "ascii",
    timeout: float = 10.0,
    interval: float = 0.2,
) -> int:
    deadline = time.time() + max(0.0, timeout)
    last_port: Optional[int] = None

    while time.time() < deadline:
        last_port = resolve_ascii_port(instance, comm_key=comm_key)
        if last_port is not None and last_port > 0:
            return last_port
        time.sleep(max(0.0, interval))

    raise TimeoutError(
        "Unable to resolve ASCII port from instance communication; "
        f"last port={last_port!r}."
    )


__all__ = ["resolve_ascii_port", "wait_for_ascii_port"]

