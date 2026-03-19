# SPDX-License-Identifier: MIT

from __future__ import annotations

import yaml

from tests.common.repo import repo_root


ROOT = repo_root()
MODEL_PATH = (
    ROOT
    / "library"
    / "domains"
    / "energy"
    / "evse"
    / "siemens"
    / "siemens_versicharge_ac__modbus.yaml"
)
MODEL_REL_PATH = "library/domains/energy/evse/siemens/siemens_versicharge_ac__modbus.yaml"


def test_siemens_versicharge_ac_modbus_model_loads() -> None:
    doc = yaml.safe_load(MODEL_PATH.read_text(encoding="utf-8"))

    assert isinstance(doc, dict)
    assert doc.get("name") == "siemens_versicharge_ac__modbus"

    meta_parameters = doc.get("meta_parameters")
    assert isinstance(meta_parameters, dict)
    assert meta_parameters["modbus_port"]["default"] == 5036
    assert meta_parameters["modbus_unit_id"]["default"] == 1

    attributes = doc.get("attributes")
    assert isinstance(attributes, dict)
    assert attributes["k__max_charging_current_a"] == 16
    assert attributes["energy_consumed_kwh"] == 0.0

    communication = doc.get("communication")
    assert isinstance(communication, list) and communication
    modbus = communication[0].get("modbus_slave")
    assert isinstance(modbus, dict)

    mapping = modbus.get("mapping")
    assert isinstance(mapping, dict)
    assert mapping["cmd__pause"]["address"] == [41630, 41630]
    assert mapping["k__max_charging_current_a"]["address"] == [41634, 41634]
    assert mapping["_modbus_active_power_sum_raw"]["address"] == [41666, 41666]
    assert mapping["_modbus_energy_consumed_raw"]["address"] == [41693, 41694]

    scenarios = doc.get("scenarios")
    assert isinstance(scenarios, dict)
    assert scenarios["fast_charge"]["display_name"] == "Fast 24 A Charging"
    assert scenarios["paused"]["display_name"] == "Charging Paused"
    assert scenarios["fast_charge"]["enabled"] is False
    assert scenarios["paused"]["enabled"] is False


def test_siemens_versicharge_ac_modbus_model_in_catalog() -> None:
    catalog_path = ROOT / "library" / "catalog" / "models.yaml"
    catalog = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    assert isinstance(catalog, dict)
    models = catalog.get("models")
    assert isinstance(models, list)

    matches = [
        model
        for model in models
        if isinstance(model, dict) and model.get("path") == MODEL_REL_PATH
    ]
    assert matches, "Model is missing from library/catalog/models.yaml"

    entry = matches[0]
    assert entry.get("id") == "Energy.EVSE.SiemensVersiChargeAc.Modbus"
    assert entry.get("domain") == "energy"
    assert entry.get("device_class") == "evse"
    assert entry.get("vendor") == "siemens"
