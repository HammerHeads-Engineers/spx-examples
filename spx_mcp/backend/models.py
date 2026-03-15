# SPDX-License-Identifier: MIT
"""Model helpers for repo-aware SPX MCP operations."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict
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
    from spx_python.helpers import ensure_model, load_model_definition

    model_path = catalog.get_model_path(model_id)
    validation = validate_model_path(model_path)
    if validate and not validation["ok"]:
        raise ModelValidationError(validation["errors"])

    definition = load_model_definition(model_path)
    changed = ensure_model(client, model_id, definition)
    return {
        "model_id": model_id,
        "model_path": str(model_path),
        "changed": changed,
        "validation": validation,
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
