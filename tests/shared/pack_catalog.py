# SPDX-License-Identifier: MIT
"""Shared helpers for validating pack/catalog consistency in tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from tests.common.repo import repo_root


def load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_catalog_models(*, root: Optional[Path] = None) -> List[Dict[str, Any]]:
    root = root or repo_root()
    doc = load_yaml(root / "library" / "catalog" / "models.yaml")
    if not isinstance(doc, dict):
        raise TypeError("library/catalog/models.yaml must contain a YAML mapping at the top level")
    models = doc.get("models", [])
    if not isinstance(models, list):
        raise TypeError("library/catalog/models.yaml must contain a 'models' list")
    return [m for m in models if isinstance(m, dict)]


def load_catalog_services(*, root: Optional[Path] = None) -> List[Dict[str, Any]]:
    root = root or repo_root()
    doc = load_yaml(root / "library" / "catalog" / "services.yaml")
    if not isinstance(doc, dict):
        raise TypeError("library/catalog/services.yaml must contain a YAML mapping at the top level")
    services = doc.get("services", [])
    if not isinstance(services, list):
        raise TypeError("library/catalog/services.yaml must contain a 'services' list")
    return [s for s in services if isinstance(s, dict)]


def load_catalog_industries(*, root: Optional[Path] = None) -> List[Dict[str, Any]]:
    root = root or repo_root()
    doc = load_yaml(root / "library" / "catalog" / "industries.yaml")
    if not isinstance(doc, dict):
        raise TypeError("library/catalog/industries.yaml must contain a YAML mapping at the top level")
    industries = doc.get("industries", [])
    if not isinstance(industries, list):
        raise TypeError("library/catalog/industries.yaml must contain an 'industries' list")
    return [i for i in industries if isinstance(i, dict)]


def find_industry(pack_id: str, *, root: Optional[Path] = None) -> Dict[str, Any]:
    for industry in load_catalog_industries(root=root):
        if industry.get("id") == pack_id:
            return industry
    raise KeyError(f"Pack '{pack_id}' is missing from library/catalog/industries.yaml")


def model_index_by_id(*, root: Optional[Path] = None) -> Dict[str, Dict[str, Any]]:
    index: Dict[str, Dict[str, Any]] = {}
    for model in load_catalog_models(root=root):
        model_id = model.get("id")
        if isinstance(model_id, str) and model_id:
            index[model_id] = model
    return index


def model_index_by_path(*, root: Optional[Path] = None) -> Dict[str, Dict[str, Any]]:
    index: Dict[str, Dict[str, Any]] = {}
    for model in load_catalog_models(root=root):
        path = model.get("path")
        if isinstance(path, str) and path:
            index[path] = model
    return index


def models_for_pack(pack_id: str, *, root: Optional[Path] = None) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    for model in load_catalog_models(root=root):
        packages = model.get("packages", [])
        if isinstance(packages, list) and pack_id in packages:
            result.append(model)
    return result
