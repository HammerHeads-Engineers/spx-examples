# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path

import yaml

from tests.common.repo import repo_root


ROOT = repo_root()


def _load_yaml(relative_path: str) -> dict:
    path = ROOT / Path(relative_path)
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_environment_sensor_mqtt_uses_typed_attributes() -> None:
    model = _load_yaml("library/domains/environment/sensor/generic/environment_sensor__mqtt.yaml")
    attributes = model["attributes"]

    assert attributes["k__temperature_c"]["unit"] == "degC"
    assert attributes["k__humidity_percent"]["unit"] == "percent"
    assert attributes["k__co2_ppm"]["unit"] == "ppm"
    assert attributes["k__comfort_index"]["unit"] == "score"
    assert attributes["stale_timeout"]["unit"] == "s"
    assert attributes["command_source"]["type"] == "str"


def test_vendor_dmm_models_define_typed_measurement_attributes() -> None:
    for relative_path in [
        "library/domains/lab/digital_multimeter/rohde_schwarz/rohde_schwarz_hmc8012__scpi.yaml",
        "library/domains/lab/digital_multimeter/siglent/siglent_sdm3055__scpi.yaml",
        "library/domains/lab/digital_multimeter/tektronix/tektronix_dmm4050__scpi.yaml",
    ]:
        model = _load_yaml(relative_path)
        attributes = model["attributes"]

        assert attributes["k__range_v"]["unit"] == "V"
        assert attributes["k__range_a"]["unit"] == "A"
        assert attributes["k__range_ohm"]["unit"] == "ohm"
        assert attributes["frequency_hz"]["unit"] == "Hz"
        assert attributes["period_s"]["unit"] == "s"
        assert model["actions"][0]["description"]


def test_scpi_bench_instruments_define_typed_io_attributes_and_action_descriptions() -> None:
    electronic_load = _load_yaml(
        "library/domains/lab/electronic_load/siglent/siglent_sdl1000x__scpi.yaml"
    )
    assert electronic_load["attributes"]["k__power_set_w"]["unit"] == "W"
    assert electronic_load["attributes"]["resistance_ohm"]["unit"] == "ohm"
    assert all(action["description"] for action in electronic_load["actions"])

    function_generator = _load_yaml(
        "library/domains/lab/function_generator/siglent/siglent_sdg1032x__scpi.yaml"
    )
    assert function_generator["attributes"]["k__ch1_frequency_hz"]["unit"] == "Hz"
    assert function_generator["attributes"]["k__ch1_amplitude_vpp"]["unit"] == "Vpp"
    assert function_generator["attributes"]["ch2_period_s"]["unit"] == "s"
    assert all(action["description"] for action in function_generator["actions"])

    keysight_psu = _load_yaml(
        "library/domains/lab/power_supply/keysight/keysight_e36312a__scpi.yaml"
    )
    assert keysight_psu["attributes"]["k__selected_output"]["type"] == "int"
    assert keysight_psu["attributes"]["k__ch1_voltage_set_v"]["unit"] == "V"
    assert keysight_psu["attributes"]["ch3_current_readback_a"]["unit"] == "A"
    assert all(action["description"] for action in keysight_psu["actions"])
