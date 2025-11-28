# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Hammerheads Engineers Sp. z o.o.
# See the accompanying LICENSE file for terms.

"""Shared helpers for preparing SPX models and instances in integration tests."""
from __future__ import annotations

import hashlib
import json
import time
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


def ensure_instance(
    client,
    instance_key: str,
    model_key: str,
    *,
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

        instances[instance_key] = model_key
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
            state = inst.get().get("state")
        except Exception:
            state = None
        if state not in {"running", "RUNNING"}:
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
        overrides=overrides,
        recreate=model_changed,
    )

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
