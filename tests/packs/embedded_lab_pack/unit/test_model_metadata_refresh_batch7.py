# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path

import yaml

from tests.common.repo import repo_root


ROOT = repo_root()


def _load_yaml(relative_path: str) -> dict:
    path = ROOT / Path(relative_path)
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_prevac_power_supply_models_use_typed_process_attributes() -> None:
    m1600 = _load_yaml(
        "library/domains/lab/magnetron_power_supply/prevac/prevac_m1600pdc_ps__modbus.yaml"
    )
    assert m1600["attributes"]["magnetron_power_w"]["unit"] == "W"
    assert m1600["attributes"]["k__frequency_khz"]["unit"] == "kHz"
    assert m1600["attributes"]["k__arc_off_time_ms"]["unit"] == "ms"
    assert m1600["attributes"]["operate_time_s"]["unit"] == "s"

    m600 = _load_yaml(
        "library/domains/lab/magnetron_power_supply/prevac/prevac_m600dc_ps__modbus.yaml"
    )
    assert m600["attributes"]["magnetron_voltage_v"]["unit"] == "V"
    assert m600["attributes"]["k__current_limit_output_1_ma"]["unit"] == "mA"
    assert m600["attributes"]["k__power_ramp_w_s"]["unit"] == "W/s"
    assert m600["attributes"]["extension_module_count"]["type"] == "int"


def test_prevac_tsp04_uses_typed_dual_pump_attributes() -> None:
    model = _load_yaml(
        "library/domains/lab/sublimation_pump_power_supply/prevac/prevac_tsp04_ps__modbus.yaml"
    )
    attributes = model["attributes"]

    assert attributes["k__pump1_output_current_set_a"]["unit"] == "A"
    assert attributes["pump1_actual_cycle_number"]["unit"] == "count"
    assert attributes["pump1_filament_1_total_work_time_s"]["unit"] == "s"
    assert attributes["pump2_output_voltage_v"]["unit"] == "V"
    assert attributes["pump2_actual_operate_time_s"]["unit"] == "s"


def test_embedded_lab_pack_models_no_longer_use_scalar_only_attributes() -> None:
    pack_index = _load_yaml("library/industries/embedded_lab_pack/MODELS.yaml")
    catalog = _load_yaml("library/catalog/models.yaml")
    index = {entry["id"]: entry for entry in catalog["models"]}

    scalar_only = []
    for entry in pack_index["models"]:
        model = _load_yaml(index[entry["id"]]["path"])
        attributes = model.get("attributes") or {}
        if attributes and all(not isinstance(value, dict) for value in attributes.values()):
            scalar_only.append(entry["id"])

    assert scalar_only == []
