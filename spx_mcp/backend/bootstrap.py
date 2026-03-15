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
from spx_mcp.backend.models import register_model_from_catalog


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
    from spx_python.helpers import ensure_instance as ensure_instance_basic
    from spx_python.helpers import load_model_definition

    model_payload = load_model_definition(model_path)
    has_meta = isinstance(model_payload, dict) and bool(model_payload.get("meta_parameters"))
    if has_meta:
        params, missing = meta_parameter_defaults(model_payload, overrides=meta_parameters)
        if missing:
            raise RuntimeError(
                "Missing defaults for required meta_parameters in "
                f"{model_id}: {', '.join(missing)}"
            )

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
            instances.generate(
                template=model_id,
                count=1,
                name=instance_key,
                parameters=params,
            )
            inst = instances[instance_key]
            if overrides:
                for attr_path, value in overrides.items():
                    inst.put_attr(attr_path, value)
            if reset_on_create:
                inst.reset()
            if start_on_create:
                inst.start()
            return inst

        inst = existing
        if overrides:
            for attr_path, value in overrides.items():
                inst.put_attr(attr_path, value)
        if ensure_running:
            try:
                if str(inst.state).lower() != "running":
                    inst.start()
            except Exception:
                pass
        return inst

    return ensure_instance_basic(
        client,
        instance_key,
        model_id,
        overrides=overrides,
        recreate=recreate,
        ensure_running=ensure_running,
        reset_on_create=reset_on_create,
        start_on_create=start_on_create,
    )


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
    registration = register_model_from_catalog(client, catalog, model_id)
    instance = ensure_instance(
        client,
        model_id=model_id,
        instance_key=instance_key,
        model_path=catalog.get_model_path(model_id),
        overrides=overrides,
        meta_parameters=meta_parameters,
        recreate=recreate,
        ensure_running=start,
        start_on_create=start,
    )
    return {
        "model": registration,
        "instance": {
            "instance_key": instance_key,
            "model_id": model_id,
            "state": getattr(instance, "state", None),
        },
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
