# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path

import yaml

from tests.common.repo import repo_root


ROOT = repo_root()


def _load_yaml(relative_path: str) -> dict:
    path = ROOT / Path(relative_path)
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_embedded_lab_pack_scenarios_use_display_names() -> None:
    pack_index = _load_yaml("library/industries/embedded_lab_pack/MODELS.yaml")
    catalog = _load_yaml("library/catalog/models.yaml")
    index = {entry["id"]: entry for entry in catalog["models"]}

    missing_display_names: list[str] = []
    for entry in pack_index["models"]:
        model = _load_yaml(index[entry["id"]]["path"])
        for scenario_name, scenario in (model.get("scenarios") or {}).items():
            if isinstance(scenario, dict) and "display_name" not in scenario:
                missing_display_names.append(f"{entry['id']}:{scenario_name}")

    assert missing_display_names == []


def test_environment_sensor_mqtt_bindings_are_named() -> None:
    model = _load_yaml(
        "library/domains/environment/sensor/generic/environment_sensor__mqtt.yaml"
    )
    communication = model["communication"]
    mqtt = communication[0]["mqtt"]
    bindings = mqtt["bindings"]

    assert bindings
    assert all("name" in binding for binding in bindings)
    assert bindings[0]["name"] == "publish_temperature_c"
    assert bindings[-1]["name"] == "subscribe_command_source"


def test_recent_protocol_cleanup_models_use_parameterized_endpoints() -> None:
    mcd7 = _load_yaml("library/domains/lab/detector/prevac/prevac_mcd7__modbus.yaml")
    mcd7_meta = mcd7["meta_parameters"]
    mcd7_modbus = mcd7["communication"][0]["modbus_slave"]
    assert mcd7_meta["modbus_port"]["default"] == 5022
    assert mcd7_meta["modbus_unit_id"]["default"] == 1
    assert mcd7_modbus["port"] == "$param(modbus_port)"
    assert mcd7_modbus["unit_id"] == "$param(modbus_unit_id)"

    vacuum = _load_yaml("library/domains/industrial/sensor/generic/vacuum_gauge__modbus.yaml")
    vacuum_meta = vacuum["meta_parameters"]
    vacuum_modbus = vacuum["communication"][0]["modbus_slave"]
    assert vacuum_meta["modbus_port"]["default"] == 5021
    assert vacuum_meta["modbus_unit_id"]["default"] == 1
    assert vacuum_modbus["port"] == "$param(modbus_port)"
    assert vacuum_modbus["unit_id"] == "$param(modbus_unit_id)"
