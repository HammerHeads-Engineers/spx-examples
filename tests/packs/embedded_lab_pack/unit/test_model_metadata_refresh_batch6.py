# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path

import yaml

from tests.common.repo import repo_root


ROOT = repo_root()


def _load_yaml(relative_path: str) -> dict:
    path = ROOT / Path(relative_path)
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_prevac_bcu14_uses_typed_zone_attributes_and_named_scenarios() -> None:
    model = _load_yaml("library/domains/lab/controller/prevac/prevac_bcu14__modbus.yaml")
    attributes = model["attributes"]

    assert attributes["zone1_remaining_reg_time_s"]["unit"] == "s"
    assert attributes["k__zone1_target_temp_c"]["unit"] == "degC"
    assert attributes["k__zone2_fan_start_temp_c"]["unit"] == "degC"
    assert attributes["_zone1_temp_response_gain"]["unit"] == "ratio"
    assert model["scenarios"]["zone1_bakeout"]["display_name"] == "Zone 1 Bakeout"
    assert model["scenarios"]["zone2_bakeout"]["display_name"] == "Zone 2 Bakeout"


def test_prevac_xr40b_ec_uses_typed_process_attributes() -> None:
    model = _load_yaml(
        "library/domains/lab/xray_source_emission_controller/prevac/prevac_xr40b_ec__modbus.yaml"
    )
    attributes = model["attributes"]

    assert attributes["supported_source_count"]["unit"] == "count"
    assert attributes["emission_current_ma"]["unit"] == "mA"
    assert attributes["cooling_water_temperature_c"]["unit"] == "degC"
    assert attributes["cooling_water_pressure_bar"]["unit"] == "bar"
    assert attributes["cooling_water_flow_l_min"]["unit"] == "L/min"
    assert attributes["k__emission_voltage_ramp_rate_v_s_source1"]["unit"] == "V/s"
    assert attributes["operate_time_s"]["unit"] == "s"
