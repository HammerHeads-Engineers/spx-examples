# SPDX-License-Identifier: MIT

from __future__ import annotations

import yaml

from tests.common.repo import repo_root

ROOT = repo_root()
MODEL_PATH = (
    ROOT
    / "library"
    / "domains"
    / "industrial"
    / "controller"
    / "eurotherm"
    / "eurotherm_3216__modbus.yaml"
)


def test_eurotherm_3216_modbus_model_uses_key_and_hidden_attributes() -> None:
    doc = yaml.safe_load(MODEL_PATH.read_text(encoding="utf-8"))

    assert isinstance(doc, dict)
    assert doc.get("name") == "eurotherm_3216__modbus"

    meta_parameters = doc.get("meta_parameters")
    assert isinstance(meta_parameters, dict)
    assert meta_parameters["modbus_port"]["default"] == 5029
    assert meta_parameters["modbus_unit_id"]["default"] == 1

    attributes = doc.get("attributes")
    assert isinstance(attributes, dict)

    for key_attr in ("k__setpoint_c", "k__manual_out_pct", "k__auto_man"):
        assert key_attr in attributes

    for observed_attr in ("temperature_c", "working_setpoint_c", "output_pct"):
        assert observed_attr in attributes

    for hidden_attr in (
        "_power_integral",
        "_power_derivative",
        "_power_error_prev",
        "_scale_0p1",
        "_pv_raw",
        "_target_sp_raw",
        "_manual_out_raw",
        "_working_out_raw",
        "_working_sp_raw",
        "_auto_man_raw",
    ):
        assert hidden_attr in attributes

    for legacy_public_attr in (
        "setpoint_c",
        "manual_out_pct",
        "auto_man",
        "pv_raw",
        "target_sp_raw",
        "manual_out_raw",
        "working_out_raw",
        "working_sp_raw",
        "auto_man_raw",
    ):
        assert legacy_public_attr not in attributes


def test_eurotherm_3216_modbus_model_maps_hidden_raw_registers_and_documents_scenarios() -> (
    None
):
    doc = yaml.safe_load(MODEL_PATH.read_text(encoding="utf-8"))

    assert isinstance(doc, dict)
    communication = doc.get("communication")
    assert isinstance(communication, list) and communication

    modbus = communication[0].get("modbus_slave")
    assert isinstance(modbus, dict)
    mapping = modbus.get("mapping")
    assert isinstance(mapping, dict)

    assert mapping["_pv_raw"]["address"] == [1, 1]
    assert mapping["_target_sp_raw"]["address"] == [2, 2]
    assert mapping["_manual_out_raw"]["address"] == [3, 3]
    assert mapping["_working_out_raw"]["address"] == [4, 4]
    assert mapping["_working_sp_raw"]["address"] == [5, 5]
    assert mapping["_auto_man_raw"]["address"] == [273, 273]

    scenarios = doc.get("scenarios")
    assert isinstance(scenarios, dict)
    assert "manual_to_auto_transfer" in scenarios
    assert "setpoint_ramp_up" in scenarios
    assert "ambient_disturbance" in scenarios

    for name, scenario in scenarios.items():
        assert isinstance(scenario, dict), f"Scenario {name!r} must be a mapping"
        assert (
            isinstance(scenario.get("display_name"), str) and scenario["display_name"]
        )
        assert isinstance(scenario.get("description"), str) and scenario["description"]
        assert scenario.get("enabled") is not True


def test_eurotherm_3216_modbus_model_is_in_catalog() -> None:
    catalog_path = ROOT / "library" / "catalog" / "models.yaml"
    catalog = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))

    assert isinstance(catalog, dict)
    models = catalog.get("models")
    assert isinstance(models, list)

    matches = [
        model
        for model in models
        if isinstance(model, dict)
        and model.get("path")
        == "library/domains/industrial/controller/eurotherm/eurotherm_3216__modbus.yaml"
    ]
    assert matches, "Model is missing from library/catalog/models.yaml"
