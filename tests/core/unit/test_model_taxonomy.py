# SPDX-License-Identifier: MIT
"""Validate model taxonomy metadata in the catalog."""

from __future__ import annotations

import re
from collections import Counter

from tests.shared.pack_catalog import load_catalog_models

ALLOWED_DOMAIN_GROUPS = {
    "building",
    "environment",
    "industrial",
    "energy",
    "lab",
}
SLUG_RE = re.compile(r"^[a-z0-9_]+$")
MODEL_PATH_RE = re.compile(
    r"^library/domains/(?P<domain>[a-z0-9_]+)/(?P<device_class>[a-z0-9_]+)/(?P<vendor>[a-z0-9_]+)/[a-z0-9_]+\.yaml$"
)


def test_catalog_models_include_taxonomy_metadata() -> None:
    models = load_catalog_models()
    assert models, "No catalog models found."

    for model in models:
        model_id = model.get("id", "<missing>")

        domain_group = model.get("domain_group")
        assert (
            isinstance(domain_group, str) and domain_group
        ), f"Model '{model_id}' is missing domain_group"
        assert (
            domain_group in ALLOWED_DOMAIN_GROUPS
        ), f"Model '{model_id}' has invalid domain_group '{domain_group}'"

        device_class = model.get("device_class")
        assert (
            isinstance(device_class, str) and device_class
        ), f"Model '{model_id}' is missing device_class"
        assert SLUG_RE.match(
            device_class
        ), f"Model '{model_id}' has invalid device_class '{device_class}'"

        vendor = model.get("vendor")
        assert (
            isinstance(vendor, str) and vendor
        ), f"Model '{model_id}' is missing vendor"
        assert SLUG_RE.match(
            vendor
        ), f"Model '{model_id}' has invalid vendor '{vendor}'"


def test_catalog_model_ids_and_paths_are_unique() -> None:
    models = load_catalog_models()

    id_counts = Counter(model.get("id") for model in models)
    duplicate_ids = sorted(
        model_id for model_id, count in id_counts.items() if model_id and count > 1
    )
    assert not duplicate_ids, f"Duplicate model ids found: {duplicate_ids}"

    path_counts = Counter(model.get("path") for model in models)
    duplicate_paths = sorted(
        path for path, count in path_counts.items() if path and count > 1
    )
    assert not duplicate_paths, f"Duplicate model paths found: {duplicate_paths}"


def test_catalog_model_paths_follow_semantic_tree() -> None:
    for model in load_catalog_models():
        model_id = model.get("id", "<missing>")
        path = model.get("path")
        assert isinstance(path, str) and path, f"Model '{model_id}' is missing path"

        match = MODEL_PATH_RE.match(path)
        assert match, (
            f"Model '{model_id}' path '{path}' must match "
            "library/domains/<domain_group>/<device_class>/<vendor>/<file>.yaml"
        )

        domain_group = model.get("domain_group")
        device_class = model.get("device_class")
        vendor = model.get("vendor")
        domain = model.get("domain")

        assert (
            domain == domain_group
        ), f"Model '{model_id}' has domain '{domain}' but domain_group '{domain_group}'"
        assert match.group("domain") == domain_group, (
            f"Model '{model_id}' path domain '{match.group('domain')}' "
            f"does not match domain_group '{domain_group}'"
        )
        assert match.group("device_class") == device_class, (
            f"Model '{model_id}' path device_class '{match.group('device_class')}' "
            f"does not match device_class '{device_class}'"
        )
        assert match.group("vendor") == vendor, (
            f"Model '{model_id}' path vendor '{match.group('vendor')}' "
            f"does not match vendor '{vendor}'"
        )
