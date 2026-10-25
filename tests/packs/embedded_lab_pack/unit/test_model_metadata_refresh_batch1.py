# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path

import yaml

from tests.common.repo import repo_root


ROOT = repo_root()


def _load_yaml(relative_path: str) -> dict:
    path = ROOT / Path(relative_path)
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_batch1_models_define_name_and_description() -> None:
    model_paths = [
        "library/domains/lab/sensor/generic/temperature_sensor__ble_gatt.yaml",
        "library/domains/lab/monitor/generic/vital_signs_monitor__ble_gatt.yaml",
        "library/domains/environment/sensor/generic/environment_sensor__lwm2m.yaml",
        "library/domains/environment/sensor/generic/environment_sensor__mqtt.yaml",
        "library/domains/industrial/sensor/generic/vacuum_gauge__modbus.yaml",
    ]

    for relative_path in model_paths:
        doc = _load_yaml(relative_path)
        assert doc.get("name"), f"Missing name in {relative_path}"
        assert doc.get("description"), f"Missing description in {relative_path}"


def test_batch1_models_expose_typed_key_attributes() -> None:
    temperature_sensor = _load_yaml(
        "library/domains/lab/sensor/generic/temperature_sensor__ble_gatt.yaml"
    )
    assert temperature_sensor["attributes"]["temperature"]["type"] == "float"
    assert temperature_sensor["attributes"]["temperature"]["unit"] == "degC"
    assert temperature_sensor["attributes"]["setpoint"]["default"] == 24.0

    vital_signs = _load_yaml(
        "library/domains/lab/monitor/generic/vital_signs_monitor__ble_gatt.yaml"
    )
    assert vital_signs["attributes"]["heartRateBpm"]["type"] == "float"
    assert vital_signs["attributes"]["heartRateBpm"]["unit"] == "bpm"
    assert vital_signs["attributes"]["bloodOxygenPercent"]["unit"] == "percent"

    lwm2m_sensor = _load_yaml(
        "library/domains/environment/sensor/generic/environment_sensor__lwm2m.yaml"
    )
    assert lwm2m_sensor["attributes"]["k__temperature_c"]["type"] == "float"
    assert lwm2m_sensor["attributes"]["k__temperature_c"]["unit"] == "degC"
    assert lwm2m_sensor["attributes"]["k__hvac_mode"]["type"] == "str"

    vacuum_gauge = _load_yaml(
        "library/domains/industrial/sensor/generic/vacuum_gauge__modbus.yaml"
    )
    assert vacuum_gauge["attributes"]["rough_pressure"]["type"] == "float"
    assert vacuum_gauge["attributes"]["rough_pressure"]["unit"] == "mbar"
    assert vacuum_gauge["attributes"]["ionizer_enabled"]["type"] == "int"


def test_environment_sensor_mqtt_actions_and_scenarios_are_named() -> None:
    mqtt_sensor = _load_yaml("library/domains/environment/sensor/generic/environment_sensor__mqtt.yaml")

    actions = mqtt_sensor.get("actions")
    assert isinstance(actions, list)
    action_names = {action.get("name") for action in actions if isinstance(action, dict)}
    assert "update_occupancy_count" in action_names
    assert "update_temperature" in action_names
    assert "update_humidity" in action_names
    assert "update_co2_ppm" in action_names
    assert "raise_stale_data_alarm" in action_names

    scenarios = mqtt_sensor.get("scenarios")
    assert isinstance(scenarios, dict)
    assert scenarios["occupancy_spike"]["name"] == "Occupancy Spike"
    assert scenarios["night_setback"]["name"] == "Night Setback"
    assert scenarios["mqtt_disconnect"]["name"] == "MQTT Disconnect"


def test_vital_lwm2m_and_vacuum_gauge_scenarios_are_named() -> None:
    vital_signs = _load_yaml(
        "library/domains/lab/monitor/generic/vital_signs_monitor__ble_gatt.yaml"
    )
    assert vital_signs["scenarios"]["deep_sleep"]["name"] == "Deep Sleep"
    assert vital_signs["scenarios"]["interval_training"]["name"] == "Interval Training"

    lwm2m_sensor = _load_yaml(
        "library/domains/environment/sensor/generic/environment_sensor__lwm2m.yaml"
    )
    assert lwm2m_sensor["scenarios"]["lwm2m_reconnect"]["name"] == "LwM2M Reconnect"

    vacuum_gauge = _load_yaml(
        "library/domains/industrial/sensor/generic/vacuum_gauge__modbus.yaml"
    )
    scenario_defs = vacuum_gauge["scenarios"]
    assert scenario_defs["discharge_spike"]["name"] == "Discharge Spike"
    assert scenario_defs["sensor_drift"]["name"] == "Sensor Drift"

    actions = vacuum_gauge["actions"]
    named_set_actions = [
        action for action in actions if isinstance(action, dict) and action.get("name") == "Discharge Trigger Reset"
    ]
    assert named_set_actions, "Expected the discharge trigger reset action to be named"
