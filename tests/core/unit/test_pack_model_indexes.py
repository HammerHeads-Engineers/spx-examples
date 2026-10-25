# SPDX-License-Identifier: MIT
"""Validate pack model indexes and pack directory layout."""

from __future__ import annotations

from tests.common.repo import repo_root
from tests.shared import pack_catalog

ROOT = repo_root()
PACK_INDEX_FIELDS = ("id", "path", "domain_group", "device_class", "vendor")
ALLOWED_PACK_FILES = {"README.md", "SPEC.md", "MODELS.yaml"}


def _expected_pack_index(pack_id: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for model in pack_catalog.models_for_pack(pack_id):
        row = {field: str(model.get(field, "")) for field in PACK_INDEX_FIELDS}
        rows.append(row)
    return sorted(rows, key=lambda row: (row["id"], row["path"]))


def test_pack_directories_only_contain_docs_and_models_index() -> None:
    for industry in pack_catalog.load_catalog_industries():
        pack_path = industry.get("path")
        pack_id = industry.get("id", "<missing>")
        assert (
            isinstance(pack_path, str) and pack_path
        ), f"Pack '{pack_id}' is missing a path"

        pack_dir = ROOT / pack_path
        assert pack_dir.is_dir(), f"Pack directory is missing: {pack_dir}"

        contents = {item.name for item in pack_dir.iterdir()}
        assert (
            contents <= ALLOWED_PACK_FILES
        ), f"Pack '{pack_id}' contains unsupported files: {sorted(contents - ALLOWED_PACK_FILES)}"
        assert "MODELS.yaml" in contents, f"Pack '{pack_id}' is missing MODELS.yaml"

        yaml_files = sorted(item.name for item in pack_dir.glob("*.yaml"))
        assert yaml_files == [
            "MODELS.yaml"
        ], f"Pack '{pack_id}' contains legacy YAML files: {yaml_files}"


def test_pack_model_indexes_match_catalog_packages() -> None:
    for industry in pack_catalog.load_catalog_industries():
        pack_id = industry.get("id")
        assert isinstance(pack_id, str) and pack_id

        actual = [
            {field: str(entry.get(field, "")) for field in PACK_INDEX_FIELDS}
            for entry in pack_catalog.load_pack_index(pack_id)
        ]
        actual = sorted(actual, key=lambda row: (row["id"], row["path"]))

        assert actual == _expected_pack_index(
            pack_id
        ), f"MODELS.yaml for pack '{pack_id}' does not match library/catalog/models.yaml"
