# SPDX-License-Identifier: MIT

from __future__ import annotations

import yaml

from tests.common.repo import repo_root

ROOT = repo_root()


def test_janitza_umg604_pro_modbus_model_loads() -> None:
    path = (
        ROOT
        / "library"
        / "domains"
        / "energy"
        / "power_quality_analyzer"
        / "janitza"
        / "janitza_umg604_pro__modbus.yaml"
    )
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))

    assert isinstance(doc, dict)
    assert doc.get("name") == "janitza_umg604_pro__modbus"
    assert "attributes" in doc
    assert "actions" in doc
    assert "communication" in doc

    comm = doc["communication"]
    assert isinstance(comm, list) and comm
    modbus = comm[0].get("modbus_slave")
    assert isinstance(modbus, dict)

    mapping = modbus.get("mapping")
    assert isinstance(mapping, dict)
    assert mapping["k__voltage_l1_n_v"]["address"] == [19000, 19001]
    assert mapping["k__current_l1_a"]["address"] == [19012, 19013]
    assert mapping["k__active_power_total_w"]["address"] == [19026, 19027]
    assert mapping["k__energy_total_wh"]["address"] == [19060, 19061]


def test_janitza_umg604_pro_modbus_model_in_catalog() -> None:
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
        == "library/domains/energy/power_quality_analyzer/janitza/janitza_umg604_pro__modbus.yaml"
    ]
    assert matches, "Model is missing from library/catalog/models.yaml"
