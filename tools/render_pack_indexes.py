#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Render pack model indexes from the catalog source of truth."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover - import guard for CLI use
    raise SystemExit(
        "Missing dependency: pyyaml. Install with 'poetry install --with dev --no-root'."
    ) from exc

PACK_INDEX_FIELDS = ("id", "path", "domain_group", "device_class", "vendor")
SPDX_HEADER = "# SPDX-License-Identifier: MIT\n"


def _load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _load_catalog_models(root: Path) -> list[dict[str, Any]]:
    doc = _load_yaml(root / "library" / "catalog" / "models.yaml") or {}
    models = doc.get("models", [])
    if not isinstance(models, list):
        raise ValueError("library/catalog/models.yaml must contain a 'models' list")
    return [model for model in models if isinstance(model, dict)]


def _load_catalog_industries(root: Path) -> list[dict[str, Any]]:
    doc = _load_yaml(root / "library" / "catalog" / "industries.yaml") or {}
    industries = doc.get("industries", [])
    if not isinstance(industries, list):
        raise ValueError(
            "library/catalog/industries.yaml must contain an 'industries' list"
        )
    return [industry for industry in industries if isinstance(industry, dict)]


def _pack_index_rows(
    models: list[dict[str, Any]], pack_id: str
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for model in models:
        packages = model.get("packages", [])
        if not isinstance(packages, list) or pack_id not in packages:
            continue
        rows.append({field: model.get(field, "") for field in PACK_INDEX_FIELDS})
    return sorted(rows, key=lambda row: (str(row["id"]), str(row["path"])))


def render_pack_indexes(root: Path) -> list[Path]:
    models = _load_catalog_models(root)
    industries = _load_catalog_industries(root)
    written: list[Path] = []

    for industry in industries:
        pack_id = industry.get("id")
        path_value = industry.get("path")
        if not isinstance(pack_id, str) or not pack_id:
            continue
        if not isinstance(path_value, str) or not path_value:
            raise ValueError(f"Industry '{pack_id}' is missing 'path'")

        pack_dir = root / path_value
        pack_dir.mkdir(parents=True, exist_ok=True)
        pack_index_path = pack_dir / "MODELS.yaml"
        payload = {"models": _pack_index_rows(models, pack_id)}
        pack_index_path.write_text(
            SPDX_HEADER + yaml.safe_dump(payload, sort_keys=False, allow_unicode=False),
            encoding="utf-8",
        )
        written.append(pack_index_path)

    return written


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render library/industries/<pack>/MODELS.yaml from the catalog."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root (default: project root)",
    )
    args = parser.parse_args()

    written = render_pack_indexes(args.root.resolve())
    print(f"Rendered {len(written)} pack index file(s).")
    for path in written:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
