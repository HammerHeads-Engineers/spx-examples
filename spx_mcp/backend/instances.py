# SPDX-License-Identifier: MIT
"""SPX instance and tree inspection helpers."""

from __future__ import annotations

from numbers import Real
import time
from typing import Any, Callable, Dict, List

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


def list_instance_scenarios(instance) -> List[str]:
    """Return scenario names registered on one live instance."""
    return list(instance["scenarios"].keys())


def get_scenario_doc(instance, scenario_name: str) -> Dict[str, Any]:
    """Return the current JSON document for one runtime scenario."""
    return _get_scenario_node(instance, scenario_name).get()


def get_attribute_value(instance, attr_path: str) -> Any:
    """Resolve an attribute path against an instance and return its default read value."""
    resolved_path = resolve_attribute_read_path(attr_path)
    base_path, value_field = _split_attribute_value_path(resolved_path)
    target = instance
    segments = [segment for segment in base_path.split("/") if segment]
    if not segments:
        raise ValueError("attr_path must contain at least one segment")
    for segment in segments:
        target = target[segment]
    value = getattr(target, value_field, target)
    if isinstance(value, dict) and "value" in value:
        return value["value"]
    return value


def get_attribute_values(instance, attr_paths: List[str]) -> Dict[str, Any]:
    """Resolve multiple attribute paths against one instance."""
    return {
        str(attr_path): get_attribute_value(instance, str(attr_path))
        for attr_path in attr_paths
    }


def set_attribute_value(instance, attr_path: str, value: Any) -> str:
    """Set one instance attribute, defaulting to ``/internal_value`` writes."""
    normalized = str(attr_path or "").strip("/")
    if not normalized:
        raise ValueError("attr_path must contain at least one segment")

    resolved = resolve_attribute_write_path(normalized)
    instance.put_attr(resolved, value)
    return resolved


def set_attribute_values(instance, values: Dict[str, Any]) -> Dict[str, str]:
    """Set multiple instance attributes and return the resolved write paths."""
    return {
        str(attr_path): set_attribute_value(instance, str(attr_path), value)
        for attr_path, value in values.items()
    }


def upsert_instance_scenario(
    instance,
    scenario_name: str,
    scenario: Dict[str, Any],
    *,
    replace: bool = True,
    start: bool = False,
    stop_existing: bool = True,
) -> Dict[str, Any]:
    """Create or replace one runtime scenario on an instance."""
    normalized_name = _normalize_scenario_name(scenario_name)
    if not isinstance(scenario, dict):
        raise ValueError("scenario must be a mapping")

    scenarios = instance["scenarios"]
    existed = normalized_name in scenarios
    if existed and not replace:
        raise ValueError(f"Scenario '{normalized_name}' already exists")

    if existed:
        old_scenario = scenarios[normalized_name]
        if stop_existing:
            _invoke_optional(old_scenario, "stop")
        del scenarios[normalized_name]

    scenarios[normalized_name] = scenario
    scenario_node = scenarios[normalized_name]
    start_result = None
    if start:
        start_result = _invoke_required(scenario_node, "start")

    return {
        "scenario_name": normalized_name,
        "replaced": existed,
        "started": start,
        "start_result": start_result,
        "scenario": scenario_node.get(),
    }


def start_instance_scenario(instance, scenario_name: str) -> Dict[str, Any]:
    """Start one runtime scenario on an instance."""
    scenario = _get_scenario_node(instance, scenario_name)
    return {
        "scenario_name": _normalize_scenario_name(scenario_name),
        "result": _invoke_required(scenario, "start"),
        "scenario": scenario.get(),
    }


def stop_instance_scenario(instance, scenario_name: str) -> Dict[str, Any]:
    """Stop one runtime scenario on an instance."""
    scenario = _get_scenario_node(instance, scenario_name)
    return {
        "scenario_name": _normalize_scenario_name(scenario_name),
        "result": _invoke_required(scenario, "stop"),
        "scenario": scenario.get(),
    }


def delete_instance_scenario(
    instance,
    scenario_name: str,
    *,
    stop_if_running: bool = True,
) -> Dict[str, Any]:
    """Delete one runtime scenario from an instance."""
    normalized_name = _normalize_scenario_name(scenario_name)
    scenarios = instance["scenarios"]
    scenario = scenarios[normalized_name]
    stop_result = None
    if stop_if_running:
        stop_result = _invoke_optional(scenario, "stop")
    del scenarios[normalized_name]
    return {
        "scenario_name": normalized_name,
        "deleted": True,
        "stopped": bool(stop_if_running),
        "stop_result": stop_result,
    }


def ramp_attribute_value(
    instance,
    attr_path: str,
    target: Any,
    *,
    duration_s: float,
    steps: int = 10,
    start_value: Any = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    monotonic_fn: Callable[[], float] = time.monotonic,
) -> Dict[str, Any]:
    """Ramp one numeric attribute from its current value to the requested target."""
    if steps <= 0:
        raise ValueError("steps must be greater than 0")
    if duration_s < 0:
        raise ValueError("duration_s must be greater than or equal to 0")

    normalized_path = str(attr_path or "").strip("/")
    if not normalized_path:
        raise ValueError("attr_path must contain at least one segment")

    initial_value = (
        get_attribute_value(instance, normalized_path)
        if start_value is None
        else start_value
    )
    start_numeric = _coerce_numeric(initial_value, label="start_value")
    target_numeric = _coerce_numeric(target, label="target")
    interval_s = float(duration_s) / steps
    started_at = monotonic_fn()
    applied: List[Dict[str, Any]] = []
    resolved_path = resolve_attribute_write_path(normalized_path)

    for step in range(1, steps + 1):
        deadline = started_at + (interval_s * step)
        remaining = deadline - monotonic_fn()
        if remaining > 0:
            sleep_fn(remaining)
        value = (
            target_numeric
            if step == steps
            else round(start_numeric + ((target_numeric - start_numeric) * (step / steps)), 10)
        )
        set_attribute_value(instance, normalized_path, value)
        applied.append(
            {
                "step": step,
                "value": value,
                "elapsed_s": round(monotonic_fn() - started_at, 3),
            }
        )

    final_value = get_attribute_value(instance, normalized_path)
    return {
        "attr_path": normalized_path,
        "resolved_path": resolved_path,
        "start_value": start_numeric,
        "target_value": target_numeric,
        "duration_s": float(duration_s),
        "steps": steps,
        "interval_s": interval_s,
        "applied": applied,
        "final_value": final_value,
    }


def read_instance_node(client, instance_key: str, relative_path: str) -> Any:
    """Resolve a path relative to an instance key."""
    return read_path(client, f"instances/{instance_key}/{relative_path}")


def resolve_attribute_read_path(attr_path: str) -> str:
    """Return the effective attribute path for default reads."""
    normalized = str(attr_path or "").strip("/")
    if not normalized:
        raise ValueError("attr_path must contain at least one segment")
    if normalized.endswith("/internal_value") or normalized.endswith("/external_value"):
        return normalized
    return f"{normalized}/external_value"


def resolve_attribute_write_path(attr_path: str) -> str:
    """Return the effective attribute path for default writes."""
    normalized = str(attr_path or "").strip("/")
    if not normalized:
        raise ValueError("attr_path must contain at least one segment")
    if normalized.endswith("/internal_value") or normalized.endswith("/external_value"):
        return normalized
    return f"{normalized}/internal_value"


def _default_writable_attr_path(attr_path: str) -> str:
    """Backward-compatible alias for internal callers."""
    return resolve_attribute_write_path(attr_path)


def _default_readable_attr_path(attr_path: str) -> str:
    """Backward-compatible alias for internal callers."""
    return resolve_attribute_read_path(attr_path)


def _split_attribute_value_path(attr_path: str) -> tuple[str, str]:
    normalized = str(attr_path or "").strip("/")
    if normalized.endswith("/internal_value"):
        return normalized[: -len("/internal_value")], "internal_value"
    if normalized.endswith("/external_value"):
        return normalized[: -len("/external_value")], "external_value"
    return normalized, "external_value"


def _normalize_scenario_name(scenario_name: str) -> str:
    normalized = str(scenario_name or "").strip()
    if not normalized:
        raise ValueError("scenario_name must not be empty")
    return normalized


def _get_scenario_node(instance, scenario_name: str):
    return instance["scenarios"][_normalize_scenario_name(scenario_name)]


def _invoke_optional(target, method_name: str) -> Any:
    method = getattr(target, method_name, None)
    if callable(method):
        return method()
    return None


def _invoke_required(target, method_name: str) -> Any:
    method = getattr(target, method_name, None)
    if not callable(method):
        raise ValueError(f"Scenario does not expose callable '{method_name}()'")
    return method()


def _coerce_numeric(value: Any, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{label} must be numeric")
    return float(value)
