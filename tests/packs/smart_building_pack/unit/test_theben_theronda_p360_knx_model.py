# SPDX-License-Identifier: MIT

from __future__ import annotations

import yaml

from tests.common.repo import repo_root

ROOT = repo_root()


def test_theben_theronda_p360_knx_model_loads() -> None:
    path = (
        ROOT
        / "library"
        / "domains"
        / "building"
        / "sensor"
        / "theben"
        / "theronda_p360__knx.yaml"
    )
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))

    assert isinstance(doc, dict)
    assert doc.get("name") == "theronda_p360__knx"
    assert "attributes" in doc
    assert "actions" in doc
    assert "communication" in doc

    comm = doc["communication"]
    assert isinstance(comm, list) and comm
    knx = comm[0].get("knx_ip")
    assert isinstance(knx, dict)

    bindings = knx.get("bindings")
    assert isinstance(bindings, list) and bindings
    names = {b.get("name") for b in bindings if isinstance(b, dict)}
    assert "obj0_c1_switch" in names
    assert "obj9_brightness_value" in names


def test_theben_theronda_p360_knx_model_in_catalog() -> None:
    catalog_path = ROOT / "library" / "catalog" / "models.yaml"
    catalog = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    assert isinstance(catalog, dict)
    models = catalog.get("models")
    assert isinstance(models, list)

    matches = [
        m
        for m in models
        if isinstance(m, dict)
        and m.get("path")
        == "library/domains/building/sensor/theben/theronda_p360__knx.yaml"
    ]
    assert matches, "Model is missing from library/catalog/models.yaml"
