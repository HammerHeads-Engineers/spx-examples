# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Hammerheads Engineers Sp. z o.o.
# See the accompanying LICENSE file for terms.

"""Shared helpers for preparing SPX models and instances in integration tests."""
from __future__ import annotations

import hashlib
import json
import time
import unittest
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import yaml


def load_model_definition(model_path: Path) -> Dict[str, Any]:
    with Path(model_path).open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def extract_model_definition(model_doc: Any) -> Optional[Dict[str, Any]]:
    if isinstance(model_doc, dict):
        for key in ("definition", "model", "data"):
            candidate = model_doc.get(key)
            if isinstance(candidate, dict):
                return candidate
        return model_doc
    return None


def fingerprint_model(model_def: Optional[Dict[str, Any]]) -> Optional[str]:
    if model_def is None:
        return None
    try:
        serialised = json.dumps(model_def, sort_keys=True, separators=(",", ":"))
    except TypeError:
        return None
    return hashlib.sha256(serialised.encode("utf-8")).hexdigest()


def ensure_model(client, model_key: str, model_def: Dict[str, Any]) -> bool:
    """Ensure the given model is registered. Returns True if updated."""
    models_client = client["models"]
    current_doc = None
    try:
        current_doc = models_client[model_key].definition
    except Exception:
        current_doc = None

    current_def = extract_model_definition(current_doc)
    local_fp = fingerprint_model(model_def)
    remote_fp = fingerprint_model(current_def)

    if local_fp != remote_fp:
        models_client[model_key] = model_def
        return True
    return False


def _meta_defaults(model_def: Optional[Dict[str, Any]]) -> tuple[Dict[str, Any], list[str]]:
    meta = (model_def or {}).get("meta_parameters", {})
    if not isinstance(meta, dict):
        return {}, []

    params: Dict[str, Any] = {}
    missing: list[str] = []
    for name, spec in meta.items():
        if not isinstance(spec, dict):
            continue
        if "default" in spec:
            params[name] = {"cycle": [spec.get("default")]}
        elif spec.get("required") is True:
            missing.append(name)
    return params, missing


def _create_instance_with_meta_defaults(
    instances: Any,
    instance_key: str,
    model_key: str,
    model_def: Optional[Dict[str, Any]],
) -> None:
    has_meta = isinstance(model_def, dict) and bool(model_def.get("meta_parameters"))
    if has_meta:
        params, missing = _meta_defaults(model_def)
        if missing:
            raise RuntimeError(
                f"Missing defaults for required meta_parameters in {model_key}: {', '.join(missing)}"
            )
        generate = getattr(instances, "generate", None)
        if params and callable(generate):
            generate(
                template=model_key,
                count=1,
                name=instance_key,
                parameters=params,
            )
            return

    instances[instance_key] = model_key


def ensure_instance(
    client,
    instance_key: str,
    model_key: str,
    *,
    model_def: Optional[Dict[str, Any]] = None,
    overrides: Optional[Dict[str, Any]] = None,
    recreate: bool = False,
    ensure_running: bool = True,
    reset_on_create: bool = True,
    start_on_create: bool = True,
):
    """Ensure an instance exists for the given model and is running."""
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

        _create_instance_with_meta_defaults(instances, instance_key, model_key, model_def)
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
            instance_doc = inst.get()
            state = None
            if isinstance(instance_doc, dict):
                state = instance_doc.get("state")
                if state is None:
                    attr = instance_doc.get("attr")
                    if isinstance(attr, dict):
                        state_attr = attr.get("state")
                        if isinstance(state_attr, dict):
                            state = state_attr.get("value")
        except Exception:
            state = None
        if str(state).lower() != "running":
            try:
                inst.start()
            except Exception:
                pass
    return inst


def bootstrap_model_instance(
    spx_module,
    *,
    product_key: str,
    base_url: str,
    model_path: Path,
    model_key: str,
    instance_key: str,
    unit_id: Optional[int] = None,
    attribute_overrides: Optional[Dict[str, Any]] = None,
):
    """Load a model and ensure an instance is available, returning (client, instance, model_changed)."""
    client = spx_module.init(address=base_url, product_key=product_key)
    model_def = load_model_definition(model_path)
    model_changed = ensure_model(client, model_key, model_def)

    overrides = dict(attribute_overrides or {})
    # if unit_id is not None:
    #     overrides.setdefault("communication/modbus_slave/id", unit_id)

    instance = ensure_instance(
        client,
        instance_key,
        model_key,
        model_def=model_def,
        recreate=model_changed,
        overrides=None,
        ensure_running=False,
        reset_on_create=False,
        start_on_create=False,
    )

    # Ensure deterministic test runs even when the instance already exists from a previous run.
    # Apply overrides after reset so configuration changes (e.g. ports) are not reverted.
    try:
        instance.stop()
    except Exception:
        pass
    try:
        instance.reset()
    except Exception:
        pass
    if overrides:
        for attr_path, value in overrides.items():
            try:
                instance.put_attr(attr_path, value)
            except Exception:
                pass
    try:
        instance.start()
    except Exception:
        pass

    return client, instance, model_changed


def wait_seconds(duration: float, interval: float = 0.2) -> None:
    """Sleep for duration seconds, yielding periodically to keep loops responsive."""
    deadline = time.time() + max(0.0, duration)
    while time.time() < deadline:
        remaining = max(0.0, deadline - time.time())
        time.sleep(min(interval, remaining))


def wait_for_condition(
    predicate: Callable[[], bool],
    *,
    timeout: float = 5.0,
    interval: float = 0.1,
) -> bool:
    """Poll predicate until it returns True or timeout expires."""
    deadline = time.time() + max(0.0, timeout)
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def _extract_instance_state(instance: Any) -> Optional[str]:
    try:
        doc = instance.get()
    except Exception:
        doc = None

    if isinstance(doc, dict):
        state = doc.get("state")
        if isinstance(state, str):
            return state
        attr = doc.get("attr")
        if isinstance(attr, dict):
            state_attr = attr.get("state")
            if isinstance(state_attr, dict):
                value = state_attr.get("value")
                if isinstance(value, str):
                    return value
    state = getattr(instance, "state", None)
    if isinstance(state, str):
        return state
    return None


def _extract_instance_model_id(instance: Any) -> Optional[str]:
    model_id = getattr(instance, "model_id", None)
    if isinstance(model_id, str) and model_id:
        return model_id

    model = getattr(instance, "model", None)
    if isinstance(model, str) and model:
        return model

    try:
        doc = instance.get()
    except Exception:
        doc = None

    if isinstance(doc, dict):
        for key in ("model_id", "model", "modelId"):
            value = doc.get(key)
            if isinstance(value, str) and value:
                return value

    return None


def require_existing_instance(
    client: Any,
    instance_key: str,
    *,
    expected_model_id: Optional[str] = None,
    ensure_running: bool = True,
):
    """Return an existing instance; skip if missing, assert if model id mismatches."""
    try:
        instance = client["instances"][instance_key]
    except Exception as exc:
        raise unittest.SkipTest(
            f"SPX instance '{instance_key}' not found (did you run installer/bootstrap?): {exc}"
        ) from exc

    if expected_model_id:
        actual_model_id = _extract_instance_model_id(instance)
        if actual_model_id and actual_model_id != expected_model_id:
            raise AssertionError(
                f"SPX instance '{instance_key}' uses model '{actual_model_id}', expected '{expected_model_id}'"
            )

    if ensure_running:
        state = (_extract_instance_state(instance) or "").lower()
        if state != "running":
            try:
                instance.start()
            except Exception:
                pass

    return instance
