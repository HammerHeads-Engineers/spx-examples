# SPDX-License-Identifier: MIT

from __future__ import annotations

import yaml

from tests.common.repo import repo_root

ROOT = repo_root()


def test_apc_rack_pdu_rpdu2g_modbus_model_loads() -> None:
    path = ROOT / "library" / "domains" / "iot" / "apc" / "rack_pdu_rpdu2g__modbus.yaml"
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))

    assert isinstance(doc, dict)
    assert doc.get("name") == "rack_pdu_rpdu2g__modbus"
    assert "attributes" in doc
    assert "actions" in doc
    assert "communication" in doc

    comm = doc["communication"]
    assert isinstance(comm, list) and comm
    modbus = comm[0].get("modbus_slave")
    assert isinstance(modbus, dict)

    mapping = modbus.get("mapping")
    assert isinstance(mapping, dict)
    assert mapping["device_real_load_power_raw"]["address"] == [40208, 40208]
    assert mapping["device_energy_raw"]["address"] == [40211, 40212]
    assert mapping["phase_l1_current_raw"]["address"] == [40668, 40668]
    assert mapping["phase_l2_voltage_raw"]["address"] == [40691, 40691]
    assert mapping["phase_l3_power_raw"]["address"] == [40714, 40714]


def test_apc_rack_pdu_rpdu2g_modbus_model_in_catalog() -> None:
    catalog_path = ROOT / "library" / "catalog" / "models.yaml"
    catalog = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    assert isinstance(catalog, dict)
    models = catalog.get("models")
    assert isinstance(models, list)

    matches = [
        m
        for m in models
        if isinstance(m, dict)
        and m.get("path") == "library/domains/iot/apc/rack_pdu_rpdu2g__modbus.yaml"
    ]
    assert matches, "Model is missing from library/catalog/models.yaml"
