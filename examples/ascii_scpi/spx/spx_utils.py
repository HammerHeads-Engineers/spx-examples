"""SPX client helpers for ASCII/SCPI examples."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Optional

import yaml


def load_model_definition(model_path: str | Path) -> dict[str, Any]:
    return yaml.safe_load(Path(model_path).read_text(encoding="utf-8"))


def _extract_model_definition(model_doc: Any) -> Optional[dict[str, Any]]:
    if isinstance(model_doc, dict):
        for key in ("definition", "model", "data"):
            candidate = model_doc.get(key)
            if isinstance(candidate, dict):
                return candidate
        return model_doc
    return None


def _fingerprint_model(model_def: Optional[dict[str, Any]]) -> Optional[str]:
    if model_def is None:
        return None
    try:
        serialised = json.dumps(model_def, sort_keys=True, separators=(",", ":"))
    except TypeError:
        return None
    return hashlib.sha256(serialised.encode("utf-8")).hexdigest()


def ensure_model(client, model_key: str, model_def: dict[str, Any]) -> bool:
    models_client = client["models"]
    current_doc = None
    try:
        current_doc = models_client[model_key].definition
    except Exception:
        current_doc = None

    current_def = _extract_model_definition(current_doc)
    local_fp = _fingerprint_model(model_def)
    remote_fp = _fingerprint_model(current_def)

    if local_fp != remote_fp:
        models_client[model_key] = model_def
        return True
    return False


def ensure_instance(
    client,
    instance_key: str,
    model_key: str,
    *,
    recreate: bool,
    start: bool = True,
):
    instances = client["instances"]
    instance = None
    try:
        instance = instances[instance_key]
    except Exception:
        instance = None

    if recreate or instance is None:
        if instance is not None:
            try:
                instance.stop()
            except Exception:
                pass
            try:
                del instances[instance_key]
            except Exception:
                pass
        instances[instance_key] = model_key
        instance = instances[instance_key]

    if start:
        try:
            instance.start()
        except Exception:
            pass
    return instance


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


def resolve_ascii_port(instance: Any, comm_key: str = "ascii") -> Optional[int]:
    comms = None
    try:
        comms = instance["communication"]
    except Exception:
        if isinstance(instance, dict):
            comms = instance.get("communication")

    comm = None
    if isinstance(comms, dict) and comm_key in comms:
        comm = comms.get(comm_key)
    elif isinstance(comms, list):
        for entry in comms:
            if isinstance(entry, dict) and comm_key in entry:
                comm = entry.get(comm_key)
                break
    if comm is None:
        return None

    value = None
    try:
        value = getattr(comm, "port")
    except Exception:
        if isinstance(comm, dict):
            value = comm.get("port")

    value = _unwrap_value(value)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def wait_for_ascii_port(instance: Any, timeout: float = 10.0, interval: float = 0.2) -> int:
    deadline = time.time() + max(0.0, timeout)
    last_port = None
    while time.time() < deadline:
        last_port = resolve_ascii_port(instance)
        if last_port:
            return last_port
        time.sleep(max(0.0, interval))
    raise TimeoutError(f"Timed out waiting for ASCII port (last={last_port})")
