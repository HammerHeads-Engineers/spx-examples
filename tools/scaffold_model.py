"""Create a reviewable model/catalog draft from the minimal or an existing twin."""

from __future__ import annotations

import copy
import re
from pathlib import Path

import yaml

from tools.model_catalog import CatalogError, distribution_config, read_yaml


def refresh(root: Path) -> None:
    from tools.render_pack_indexes import render_pack_indexes
    from scripts.render_readme_catalog import refresh as refresh_readme

    render_pack_indexes(root)
    refresh_readme(root)


def scaffold(
    root: Path,
    *,
    model_id: str,
    name: str,
    description: str,
    packs: list[str],
    copy_from=None,
    domain_group=None,
    device_class=None,
    vendor=None,
) -> Path:
    root = root.resolve()
    catalog = root / "library/catalog/models.yaml"
    entries = read_yaml(catalog)["models"]
    industries = read_yaml(root / "library/catalog/industries.yaml")["industries"]
    known_packs = {pack["id"] for pack in industries}
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", model_id) or any(
        e["id"].casefold() == model_id.casefold() for e in entries
    ):
        raise CatalogError(
            "Choose a new, unique model ID using letters, digits, dots, underscores or hyphens"
        )
    if not re.fullmatch(r"[a-z][a-z0-9_]*", name) or not description.strip():
        raise CatalogError(
            "A lower_snake_case name and nonempty description are required"
        )
    if set(packs) - known_packs:
        raise CatalogError(f"Unknown packs: {sorted(set(packs) - known_packs)}")
    if copy_from:
        try:
            entry = copy.deepcopy(next(e for e in entries if e["id"] == copy_from))
        except StopIteration as exc:
            raise CatalogError(f"Unknown source model: {copy_from}") from exc
        definition = read_yaml(root / entry["path"])
    else:
        entry = {
            "domain_group": "environment",
            "device_class": "sensor",
            "vendor": "generic",
            "protocols": [],
            "services": [],
            "profiles": [],
        }
        definition = read_yaml(
            Path(__file__).resolve().parents[1]
            / "templates/models/temperature_sensor.yaml"
        )
    for key, value in (
        ("domain_group", domain_group),
        ("device_class", device_class),
        ("vendor", vendor),
    ):
        if value is not None:
            entry[key] = value
        if not re.fullmatch(r"[a-z][a-z0-9_]*", entry[key]):
            raise CatalogError(f"{key} must be lower_snake_case")
    domains = {
        entry["id"]
        for entry in read_yaml(root / "library/catalog/domains.yaml")["domains"]
    }
    if entry["domain_group"] not in domains:
        raise CatalogError(f"Unknown domain group: {entry['domain_group']}")
    relative = f"library/domains/{entry['domain_group']}/{entry['device_class']}/{entry['vendor']}/{name}.yaml"
    if (
        any(e["path"].casefold() == relative.casefold() for e in entries)
        or (root / relative).exists()
    ):
        raise CatalogError(f"{relative}: already exists; choose a new name")
    entry.update(
        {
            "id": model_id,
            "name": name.replace("_", " ").title(),
            "path": relative,
            "domain": entry["domain_group"],
            "packages": sorted(set(packs)),
            "profiles": [],
        }
    )
    definition.update({"name": name, "description": description.strip()})
    model_path = root / relative
    generated = [
        root / "README.md",
        *[root / pack["path"] / "MODELS.yaml" for pack in industries],
    ]
    backups = {
        path: path.read_bytes() if path.exists() else None
        for path in [catalog, *generated]
    }
    try:
        model_path.parent.mkdir(parents=True, exist_ok=True)
        license_id = entry.get("distribution", {}).get(
            "license", distribution_config(root)["license"]
        )
        model_path.write_text(
            f"# SPDX-License-Identifier: {license_id}\n"
            + yaml.safe_dump(definition, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        catalog.write_text(
            catalog.read_text(encoding="utf-8").rstrip()
            + "\n"
            + yaml.safe_dump([entry], sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        refresh(root)
    except Exception:
        model_path.unlink(missing_ok=True)
        for path, content in backups.items():
            if content is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(content)
        raise
    return model_path
