# SPDX-License-Identifier: MIT
"""Repo-aware bootstrap helpers that extend spx_python for MCP workflows."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from installer.selection import (
    resolve_default_instances,
    resolve_model_ids,
    resolve_start_instances,
)

from spx_mcp.backend.catalog import RepoCatalog
from spx_mcp.backend.models import load_model_definition, register_model_from_catalog


def meta_parameter_defaults(
    model_payload: Dict[str, Any],
    overrides: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], List[str]]:
    """Return SPX generate() parameter payload + a list of missing required params."""
    meta = model_payload.get("meta_parameters", {})
    if not isinstance(meta, dict):
        return {}, []

    params: Dict[str, Any] = {}
    missing: List[str] = []
    provided = dict(overrides or {})
    unknown = sorted(set(provided.keys()) - set(meta.keys()))
    if unknown:
        raise ValueError(
            "Unknown meta_parameters provided: " + ", ".join(unknown)
        )

    for name, spec in meta.items():
        if name in provided:
            params[name] = {"cycle": [provided[name]]}
            continue
        if not isinstance(spec, dict):
            continue
        if "default" in spec:
            params[name] = {"cycle": [spec.get("default")]}
        elif spec.get("required") is True:
            missing.append(name)
    return params, missing


def ensure_instance(
    client,
    *,
    model_id: str,
    instance_key: str,
    model_path,
    overrides: Optional[Dict[str, Any]] = None,
    meta_parameters: Optional[Dict[str, Any]] = None,
    recreate: bool = False,
    ensure_running: bool = True,
    reset_on_create: bool = True,
    start_on_create: bool = True,
):
    """Ensure an instance exists, using generate() when the model defines meta_parameters."""
    model_payload = load_model_definition(model_path)
    instances = client["instances"]
    try:
        existing = instances[instance_key]
    except Exception:
        existing = None

    if recreate or existing is None:
        if existing is not None:
            try:
                existing.stop()
            except Exception:
                pass
            try:
                del instances[instance_key]
            except Exception:
                pass

        _create_instance(
            instances,
            instance_key=instance_key,
            model_id=model_id,
            model_payload=model_payload,
            meta_parameters=meta_parameters,
        )
        inst = instances[instance_key]
        if reset_on_create:
            inst.reset()
        if overrides:
            for attr_path, value in overrides.items():
                inst.put_attr(attr_path, value)
        if start_on_create:
            inst.start()
        return inst

    inst = existing
    if overrides:
        for attr_path, value in overrides.items():
            inst.put_attr(attr_path, value)
    if ensure_running:
        try:
            if str(getattr(inst, "state", "")).lower() != "running":
                inst.start()
        except Exception:
            pass
    return inst


def register_model_and_ensure_instance(
    client,
    catalog: RepoCatalog,
    *,
    model_id: str,
    instance_key: str,
    start: bool = True,
    recreate: bool = False,
    overrides: Optional[Dict[str, Any]] = None,
    meta_parameters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Register one catalog model on the server, then ensure one instance exists."""
    model_path = catalog.get_model_path(model_id)
    model_payload = load_model_definition(model_path)
    registration = register_model_from_catalog(client, catalog, model_id)
    instance = ensure_instance(
        client,
        model_id=model_id,
        instance_key=instance_key,
        model_path=model_path,
        overrides=overrides,
        meta_parameters=meta_parameters,
        recreate=recreate,
        ensure_running=start,
        start_on_create=start,
    )
    instance_summary = summarize_runtime_instance(
        instance,
        model_id=model_id,
        instance_key=instance_key,
        model_payload=model_payload,
    )
    return {
        "model": registration,
        "instance": instance_summary,
    }


def bootstrap_pack(
    client,
    catalog: RepoCatalog,
    pack_id: str,
) -> Dict[str, Any]:
    """Register all models in a pack and create the pack's default instances."""
    if pack_id not in catalog.index.industries:
        raise KeyError(f"Unknown pack id: {pack_id}")

    model_ids = resolve_model_ids([pack_id], [], [], catalog.index)
    default_instances = resolve_default_instances([pack_id], catalog.index)
    start_instances = set(resolve_start_instances([pack_id], catalog.index))

    registered = []
    model_paths = {}
    for model_id in model_ids:
        result = register_model_from_catalog(client, catalog, model_id)
        registered.append(result)
        model_paths[model_id] = catalog.get_model_path(model_id)

    created = []
    for entry in default_instances:
        model_id = entry.get("model_id")
        instance_key = entry.get("instance_key")
        if not model_id or not instance_key:
            continue
        instance = ensure_instance(
            client,
            model_id=model_id,
            instance_key=instance_key,
            model_path=model_paths[model_id],
            ensure_running=instance_key in start_instances,
            start_on_create=instance_key in start_instances,
        )
        created.append(
            {
                "instance_key": instance_key,
                "model_id": model_id,
                "state": getattr(instance, "state", None),
            }
        )

    return {
        "pack_id": pack_id,
        "registered_models": registered,
        "instances": created,
        "start_instances": sorted(start_instances),
    }


def bootstrap_profile(
    client,
    catalog: RepoCatalog,
    profile_id: str,
) -> Dict[str, Any]:
    """Register all models referenced by a quickstart profile."""
    if profile_id not in catalog.index.profiles:
        raise KeyError(f"Unknown profile id: {profile_id}")

    model_ids = resolve_model_ids([], [profile_id], [], catalog.index)
    registered = []
    for model_id in model_ids:
        registered.append(register_model_from_catalog(client, catalog, model_id))
    return {
        "profile_id": profile_id,
        "registered_models": registered,
    }


def summarize_runtime_instance(
    instance,
    *,
    model_id: str,
    instance_key: str,
    model_payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return the minimal runtime summary for a model/instance fast path."""
    instance_doc = _safe_instance_doc(instance)
    return {
        "instance_key": instance_key,
        "model_id": _extract_model_id(instance_doc) or model_id,
        "state": _extract_state(instance_doc) or getattr(instance, "state", None),
        "endpoint_details": _extract_endpoint_details(
            instance_doc,
            instance=instance,
            model_payload=model_payload,
        ),
    }


def _safe_instance_doc(instance) -> Dict[str, Any]:
    try:
        payload = instance.get()
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


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


def _create_instance(
    instances,
    *,
    instance_key: str,
    model_id: str,
    model_payload: Optional[Dict[str, Any]],
    meta_parameters: Optional[Dict[str, Any]],
) -> None:
    has_meta = isinstance(model_payload, dict) and bool(model_payload.get("meta_parameters"))
    if meta_parameters and not has_meta:
        raise RuntimeError(
            f"Meta parameter overrides provided for {model_id}, but model has no meta_parameters."
        )

    if has_meta:
        params, missing = meta_parameter_defaults(model_payload, overrides=meta_parameters)
        if missing:
            raise RuntimeError(
                "Missing defaults for required meta_parameters in "
                f"{model_id}: {', '.join(missing)}"
            )
        generate = getattr(instances, "generate", None)
        if callable(generate):
            instances.generate(
                template=model_id,
                count=1,
                name=instance_key,
                parameters=params,
            )
            return

    instances[instance_key] = model_id


def runtime_bootstrap_backend_report() -> Dict[str, Any]:
    """Return a shallow diagnostics report for the runtime instance bootstrap path."""
    return {
        "ok": True,
        "checks": [
            "instance bootstrap uses direct client registry access without spx_python.helpers",
            "meta-parameter instance creation uses instances.generate when available",
            "non-meta instance creation uses direct client['instances'][instance_key] = model_id",
        ],
    }


def _extract_endpoint_details(
    instance_doc: Dict[str, Any],
    *,
    instance=None,
    model_payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Dict[str, Any]]:
    summaries: Dict[str, Dict[str, Any]] = {}
    for source in (instance_doc, instance, model_payload):
        communication = _normalize_communication_mapping(source)
        for protocol, payload in communication.items():
            summary = _summarize_protocol_endpoint(protocol, payload)
            if not summary:
                continue
            current = summaries.setdefault(protocol, {})
            for field, value in summary.items():
                current.setdefault(field, value)
    return summaries


def _summarize_protocol_endpoint(protocol: str, payload: Any) -> Dict[str, Any]:
    fields = (
        "host",
        "hostname",
        "port",
        "address",
        "unit_id",
        "slave_id",
        "topic",
        "path",
        "endpoint",
        "url",
        "base_url",
        "method",
        "enabled",
    )
    summary: Dict[str, Any] = {}
    for field in fields:
        value = _read_endpoint_field(payload, field)
        normalized = _normalize_endpoint_value(field, value)
        if normalized is not None:
            summary[field] = normalized

    if protocol == "modbus_slave" and "unit_id" not in summary:
        fallback_unit_id = _normalize_endpoint_value("unit_id", _read_endpoint_field(payload, "id"))
        if fallback_unit_id is not None:
            summary["unit_id"] = fallback_unit_id

    if "hostname" in summary and "host" not in summary:
        summary["host"] = summary["hostname"]
    summary.pop("hostname", None)
    return summary


def _normalize_communication_mapping(source: Any) -> Dict[str, Any]:
    if source is None:
        return {}

    if isinstance(source, dict) and "communication" in source:
        return _normalize_communication_container(source.get("communication"))

    if not isinstance(source, dict):
        try:
            communication = source["communication"]
        except Exception:
            communication = None
        if communication is not None:
            return _normalize_communication_container(communication)

    if isinstance(source, dict):
        return _normalize_communication_container(source)

    return {}


def _normalize_communication_container(container: Any) -> Dict[str, Any]:
    if container is None:
        return {}

    if isinstance(container, dict):
        return {
            str(protocol): payload
            for protocol, payload in container.items()
            if isinstance(protocol, str)
        }

    if isinstance(container, list):
        mapping: Dict[str, Any] = {}
        for entry in container:
            if not isinstance(entry, dict):
                continue
            for protocol, payload in entry.items():
                if isinstance(protocol, str):
                    mapping.setdefault(protocol, payload)
        return mapping

    get_fn = getattr(container, "get", None)
    if callable(get_fn):
        try:
            payload = get_fn()
        except Exception:
            payload = None
        mapping = _normalize_communication_container(payload)
        if mapping:
            return mapping

    keys_fn = getattr(container, "keys", None)
    if callable(keys_fn):
        try:
            keys = list(keys_fn())
        except Exception:
            keys = []
        mapping = {}
        for protocol in keys:
            if not isinstance(protocol, str):
                continue
            try:
                mapping[protocol] = container[protocol]
            except Exception:
                continue
        return mapping

    return {}


def _read_endpoint_field(payload: Any, field: str) -> Any:
    if payload is None:
        return None

    value = getattr(payload, field, None)
    if callable(value):
        value = None
    if value is not None:
        return value

    if isinstance(payload, dict):
        if field in payload:
            return payload.get(field)
        attr = payload.get("attr")
        if isinstance(attr, dict):
            entry = attr.get(field)
            if entry is not None:
                return entry

    try:
        attr = payload["attr"]
    except Exception:
        attr = None
    if isinstance(attr, dict) and field in attr:
        return attr.get(field)

    for nested_key in ("config", "connection", "server", "client"):
        nested = None
        if isinstance(payload, dict):
            nested = payload.get(nested_key)
        else:
            nested = getattr(payload, nested_key, None)
        if nested is None:
            continue
        nested_value = _read_endpoint_field(nested, field)
        if nested_value is not None:
            return nested_value

    get_fn = getattr(payload, "get", None)
    if callable(get_fn):
        try:
            doc = get_fn()
        except Exception:
            doc = None
        if doc is not None and doc is not payload:
            doc_value = _read_endpoint_field(doc, field)
            if doc_value is not None:
                return doc_value

    return None


def _unwrap_runtime_value(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "internal_value"):
        try:
            return getattr(value, "internal_value")
        except Exception:
            return None
    if isinstance(value, dict) and "value" in value:
        return value.get("value")
    if hasattr(value, "value"):
        try:
            return getattr(value, "value")
        except Exception:
            return None
    return value


def _normalize_endpoint_value(field: str, value: Any) -> Optional[Any]:
    raw = _unwrap_runtime_value(value)
    if raw is None:
        return None
    if isinstance(raw, str):
        stripped = raw.strip()
        if not stripped or stripped.startswith("$"):
            return None
        raw = stripped

    if field in {"port", "unit_id", "slave_id", "id"}:
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    if isinstance(raw, (str, int, float, bool)):
        return raw
    return None
