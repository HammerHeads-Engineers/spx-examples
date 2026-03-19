# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path

import yaml

from tests.common.repo import repo_root


ROOT = repo_root()


def _load_yaml(relative_path: str) -> dict:
    path = ROOT / Path(relative_path)
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_energy_pack_catalog_is_energy_native_only() -> None:
    pack_index = _load_yaml("library/industries/energy_pack/MODELS.yaml")
    model_ids = [entry["id"] for entry in pack_index["models"]]

    assert model_ids
    assert all(model_id.startswith("Energy.") for model_id in model_ids)
    assert "Env.EnvSensor.Mqtt" not in model_ids
    assert "Weather.WeatherFeed.Http" not in model_ids
    assert "Process.ThermalController.Modbus" not in model_ids
    assert "Process.ThermalController.Advanced" not in model_ids


def test_energy_pack_models_use_typed_attributes_and_labeled_scenarios() -> None:
    pack_index = _load_yaml("library/industries/energy_pack/MODELS.yaml")
    catalog = _load_yaml("library/catalog/models.yaml")
    index = {entry["id"]: entry for entry in catalog["models"]}

    scalar_attrs: list[str] = []
    missing_display_names: list[str] = []
    for entry in pack_index["models"]:
        model = _load_yaml(index[entry["id"]]["path"])
        attributes = model.get("attributes") or {}
        for attr_name, attr_spec in attributes.items():
            if not isinstance(attr_spec, dict) or "default" not in attr_spec:
                scalar_attrs.append(f"{entry['id']}:{attr_name}")
        for scenario_name, scenario in (model.get("scenarios") or {}).items():
            if isinstance(scenario, dict) and "display_name" not in scenario:
                missing_display_names.append(f"{entry['id']}:{scenario_name}")

    assert scalar_attrs == []
    assert missing_display_names == []


def test_ocpp_models_use_parameterized_transport_settings() -> None:
    csms = _load_yaml("library/domains/energy/csms/generic/csms__ocpp.yaml")
    csms_meta = csms["meta_parameters"]
    csms_ocpp = csms["communication"][0]["ocpp"]
    assert csms_meta["ocpp_server_port"]["default"] == 9000
    assert csms_meta["ocpp_subprotocol"]["default"] == "ocpp1.6"
    assert csms_ocpp["charge_point_id"] == "$param(ocpp_charge_point_id)"
    assert csms_ocpp["server"]["port"] == "$param(ocpp_server_port)"
    assert csms["attributes"]["last_meter_values"]["type"] == "list"

    evse = _load_yaml("library/domains/energy/evse/generic/evse__ocpp.yaml")
    evse_meta = evse["meta_parameters"]
    evse_ocpp = evse["communication"][0]["ocpp"]
    assert evse_meta["ocpp_endpoint"]["default"] == "ws://localhost:9000/ocpp"
    assert evse_ocpp["endpoint"] == "$param(ocpp_endpoint)"
    assert evse_ocpp["charge_point_id"] == "$param(ocpp_charge_point_id)"
    assert evse["attributes"]["meter_values_payload"]["type"] == "list"


def test_generic_energy_meter_models_are_typed_and_named() -> None:
    mqtt_model = _load_yaml("library/domains/energy/meter/generic/energy_meter_3ph__mqtt.yaml")
    mqtt_meta = mqtt_model["meta_parameters"]
    mqtt_block = mqtt_model["communication"][0]["mqtt"]
    bindings = mqtt_block["bindings"]
    assert mqtt_meta["mqtt_broker_host"]["default"] == "host.docker.internal"
    assert mqtt_model["attributes"]["voltage_l1"]["unit"] == "V"
    assert mqtt_model["attributes"]["reactive_power_kvar"]["unit"] == "kVAR"
    assert bindings[0]["name"] == "publish_voltage_l1"
    assert bindings[-1]["name"] == "subscribe_power_factor_leading"
    assert mqtt_model["scenarios"]["pv_backfeed_disturbance"]["display_name"] == "PV Backfeed Disturbance"

    modbus_model = _load_yaml("library/domains/energy/meter/generic/energy_meter_3ph__modbus.yaml")
    assert modbus_model["attributes"]["current_l2"]["unit"] == "A"
    assert modbus_model["attributes"]["cycle_time_s"]["unit"] == "s"
    assert modbus_model["scenarios"]["frequency_dip_under_overload"]["display_name"] == (
        "Frequency Dip Under Overload"
    )


def test_vendor_energy_models_use_typed_register_backed_attributes() -> None:
    diris = _load_yaml("library/domains/energy/meter/socomec/diris_a10__modbus.yaml")
    assert diris["attributes"]["k__current_l1_a"]["unit"] == "A"
    assert diris["attributes"]["k__energy_import_total_kwh"]["unit"] == "kWh"
    assert diris["attributes"]["_modbus_frequency_raw"]["type"] == "int"
    assert diris["scenarios"]["voltage_sag"]["display_name"] == "Voltage Sag"

    pm5560 = _load_yaml("library/domains/energy/meter/schneider/schneider_pm5560__modbus.yaml")
    assert pm5560["attributes"]["voltage_ll_avg_v"]["unit"] == "V"
    assert pm5560["attributes"]["k__apparent_power_total_kva"]["unit"] == "kVA"
    assert pm5560["attributes"]["_cycle_time_s"]["unit"] == "s"
    assert pm5560["scenarios"]["pv_export"]["display_name"] == "PV Export"

    versicharge = _load_yaml("library/domains/energy/evse/siemens/siemens_versicharge_ac__modbus.yaml")
    assert versicharge["attributes"]["cmd__pause"]["type"] == "int"
    assert versicharge["attributes"]["k__voltage_l1_n_v"]["unit"] == "V"
    assert versicharge["attributes"]["power_factor_sum"]["unit"] == "ratio"
    assert versicharge["attributes"]["_cycle_time_s"]["unit"] == "s"
