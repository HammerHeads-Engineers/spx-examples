# SPDX-License-Identifier: MIT
"""Model helpers for repo-aware SPX MCP operations."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

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
