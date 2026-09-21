# SPDX-License-Identifier: MIT
"""Model helpers for repo-aware SPX MCP operations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional
import yaml

from tools.validate_models import (
    ValidationResult,
    load_yaml,
    validate_model_file,
)

from spx_mcp.backend.catalog import RepoCatalog
from spx_mcp.errors import ModelValidationError


def validate_model_path(model_path: Path) -> Dict[str, Any]:
    """Run the repo's lightweight model validator for a single file."""
    result = ValidationResult()
    payload = load_yaml(model_path, result)
    if payload is not None:
        validate_model_file(model_path, payload, result)
    return {
        "path": str(model_path),
        "ok": result.ok(),
        "errors": list(result.errors),
    }


def validate_catalog_model(catalog: RepoCatalog, model_id: str) -> Dict[str, Any]:
    """Validate a model referenced by the repository catalog."""
    model_path = catalog.get_model_path(model_id)
    return validate_model_path(model_path)


def list_model_scenarios(catalog: RepoCatalog, model_id: str) -> Dict[str, Any]:
    """Return scenario names defined in one catalog model."""
    model_path, payload = _load_catalog_model_payload(catalog, model_id)
    scenarios = _get_scenarios_mapping(model_path, payload, create=False)
    return {
        "model_id": model_id,
        "model_path": str(model_path),
        "scenario_names": list(scenarios.keys()),
    }


def get_model_scenario(
    catalog: RepoCatalog,
    model_id: str,
    scenario_name: str,
) -> Dict[str, Any]:
    """Return one scenario definition from a catalog model."""
    normalized_name = _normalize_scenario_name(scenario_name)
    model_path, payload = _load_catalog_model_payload(catalog, model_id)
    scenarios = _get_scenarios_mapping(model_path, payload, create=False)
    if normalized_name not in scenarios:
        raise ValueError(f"Scenario '{normalized_name}' not found in model '{model_id}'")
    return {
        "model_id": model_id,
        "model_path": str(model_path),
        "scenario_name": normalized_name,
        "scenario": scenarios[normalized_name],
    }


def upsert_model_scenario(
    catalog: RepoCatalog,
    model_id: str,
    scenario_name: str,
    scenario: Dict[str, Any],
    *,
    replace: bool = True,
) -> Dict[str, Any]:
    """Create or replace one scenario definition in a catalog model file."""
    normalized_name = _normalize_scenario_name(scenario_name)
    if not isinstance(scenario, dict):
        raise ValueError("scenario must be a mapping")

    model_path, payload = _load_catalog_model_payload(catalog, model_id)
    scenarios = _get_scenarios_mapping(model_path, payload, create=True)
    existed = normalized_name in scenarios
    if existed and not replace:
        raise ValueError(f"Scenario '{normalized_name}' already exists in model '{model_id}'")

    changed = (not existed) or scenarios[normalized_name] != scenario
    scenarios[normalized_name] = scenario
    validation = _validate_model_payload(model_path, payload)
    if not validation["ok"]:
        raise ModelValidationError(validation["errors"])
    if changed:
        _write_model_payload(model_path, payload)
    return {
        "model_id": model_id,
        "model_path": str(model_path),
        "scenario_name": normalized_name,
        "changed": changed,
        "replaced": existed,
        "scenario": scenarios[normalized_name],
        "validation": validation,
    }


def delete_model_scenario(
    catalog: RepoCatalog,
    model_id: str,
    scenario_name: str,
) -> Dict[str, Any]:
    """Delete one scenario definition from a catalog model file."""
    normalized_name = _normalize_scenario_name(scenario_name)
    model_path, payload = _load_catalog_model_payload(catalog, model_id)
    scenarios = _get_scenarios_mapping(model_path, payload, create=False)
    if normalized_name not in scenarios:
        raise ValueError(f"Scenario '{normalized_name}' not found in model '{model_id}'")

    removed = scenarios.pop(normalized_name)
    validation = _validate_model_payload(model_path, payload)
    if not validation["ok"]:
        raise ModelValidationError(validation["errors"])
    _write_model_payload(model_path, payload)
    return {
        "model_id": model_id,
        "model_path": str(model_path),
        "scenario_name": normalized_name,
        "deleted": True,
        "scenario": removed,
        "validation": validation,
    }


def register_model_from_catalog(
    client,
    catalog: RepoCatalog,
    model_id: str,
    *,
    validate: bool = True,
) -> Dict[str, Any]:
    """Load, validate, and register a model using the repo catalog entry."""
    model_path = catalog.get_model_path(model_id)
    validation = validate_model_path(model_path)
    if validate and not validation["ok"]:
        raise ModelValidationError(validation["errors"])

    definition = load_model_definition(model_path)
    changed = ensure_model_registered(client, model_id, definition)
    return {
        "model_id": model_id,
        "model_path": str(model_path),
        "changed": changed,
        "validation": validation,
    }


def load_model_definition(model_path: Path) -> Dict[str, Any]:
    """Load one model definition from local YAML/JSON without helper dependencies."""
    with Path(model_path).open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Model definition at {model_path} must load as a mapping")
    return payload


def ensure_model_registered(client, model_id: str, definition: Dict[str, Any]) -> bool:
    """Ensure a model definition is registered on the SPX server."""
    models_client = client["models"]
    current_definition = get_registered_model_definition(models_client, model_id)
    local_fingerprint = fingerprint_model(definition)
    remote_fingerprint = fingerprint_model(current_definition)

    if local_fingerprint is not None and local_fingerprint == remote_fingerprint:
        return False

    models_client[model_id] = definition
    return True


def get_registered_model_definition(models_client, model_id: str) -> Optional[Dict[str, Any]]:
    """Return the current remote model definition when it can be resolved safely."""
    try:
        current_node = models_client[model_id]
    except Exception:
        return None

    for candidate in (
        getattr(current_node, "definition", None),
        current_node,
    ):
        current_definition = extract_model_definition(candidate)
        if current_definition is not None:
            return current_definition

    get_fn = getattr(current_node, "get", None)
    if callable(get_fn):
        try:
            current_doc = get_fn()
        except Exception:
            current_doc = None
        current_definition = extract_model_definition(current_doc)
        if current_definition is not None:
            return current_definition

    return None


def extract_model_definition(model_doc: Any) -> Optional[Dict[str, Any]]:
    """Normalize the model payload shape returned by the SPX client."""
    if isinstance(model_doc, dict):
        for key in ("definition", "model", "data"):
            candidate = model_doc.get(key)
            if isinstance(candidate, dict):
                return candidate
        return model_doc
    return None


def fingerprint_model(model_definition: Optional[Dict[str, Any]]) -> Optional[str]:
    """Return a stable fingerprint for comparison, or None when not serializable."""
    if model_definition is None:
        return None
    try:
        serialized = json.dumps(
            model_definition,
            sort_keys=True,
            separators=(",", ":"),
        )
    except TypeError:
        return None
    return serialized


def runtime_model_backend_report() -> Dict[str, Any]:
    """Return a shallow diagnostics report for the runtime model registration path."""
    return {
        "ok": True,
        "checks": [
            "local model definitions load from YAML/JSON without spx_python.helpers",
            "model registration uses direct client['models'][model_id] writes",
        ],
    }


def _load_catalog_model_payload(
    catalog: RepoCatalog,
    model_id: str,
) -> tuple[Path, Dict[str, Any]]:
    model_path = catalog.get_model_path(model_id)
    result = ValidationResult()
    payload = load_yaml(model_path, result)
    if not isinstance(payload, dict):
        if result.errors:
            raise ModelValidationError(result.errors)
        raise ValueError(f"Model '{model_id}' must load as a mapping")
    return model_path, payload


def _validate_model_payload(model_path: Path, payload: Dict[str, Any]) -> Dict[str, Any]:
    result = ValidationResult()
    validate_model_file(model_path, payload, result)
    return {
        "path": str(model_path),
        "ok": result.ok(),
        "errors": list(result.errors),
    }


def _write_model_payload(model_path: Path, payload: Dict[str, Any]) -> None:
    model_path.write_text(
        yaml.safe_dump(
            payload,
            sort_keys=False,
            allow_unicode=False,
            default_flow_style=False,
        ),
        encoding="utf-8",
    )


def _get_scenarios_mapping(
    model_path: Path,
    payload: Dict[str, Any],
    *,
    create: bool,
) -> Dict[str, Any]:
    scenarios = payload.get("scenarios")
    if scenarios is None:
        if not create:
            return {}
        scenarios = {}
        payload["scenarios"] = scenarios
    if not isinstance(scenarios, dict):
        raise ValueError(f"{model_path}: 'scenarios' must be a mapping")
    return scenarios


def _normalize_scenario_name(scenario_name: str) -> str:
    normalized = str(scenario_name or "").strip()
    if not normalized:
        raise ValueError("scenario_name must not be empty")
    return normalized
