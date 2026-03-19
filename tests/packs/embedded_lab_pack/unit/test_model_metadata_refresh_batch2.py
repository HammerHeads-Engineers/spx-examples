# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path

import yaml

from tests.common.repo import repo_root


ROOT = repo_root()


def _load_yaml(relative_path: str) -> dict:
    path = ROOT / Path(relative_path)
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_generic_scpi_models_define_aligned_names_and_typed_attributes() -> None:
    multimeter = _load_yaml("library/domains/lab/instrument/generic/multimeter__scpi.yaml")
    assert multimeter["name"] == "multimeter__scpi"
    assert multimeter["attributes"]["voltage"]["type"] == "float"
    assert multimeter["attributes"]["voltage"]["unit"] == "V"
    assert multimeter["attributes"]["measurement_mode"]["type"] == "str"

    digital_multimeter = _load_yaml(
        "library/domains/lab/digital_multimeter/generic/digital_multimeter__scpi.yaml"
    )
    assert digital_multimeter["attributes"]["k__range_v"]["unit"] == "V"
    assert digital_multimeter["attributes"]["resistance_readback_ohm"]["unit"] == "ohm"
    assert digital_multimeter["actions"][0]["description"]

    bench_power_supply = _load_yaml(
        "library/domains/lab/power_supply/generic/bench_power_supply__scpi.yaml"
    )
    assert bench_power_supply["attributes"]["k__voltage_set_v"]["unit"] == "V"
    assert bench_power_supply["attributes"]["k__current_set_a"]["unit"] == "A"
    assert bench_power_supply["attributes"]["k__output_state"]["type"] == "str"


def test_generic_scpi_multimeter_scenarios_are_named() -> None:
    multimeter = _load_yaml("library/domains/lab/instrument/generic/multimeter__scpi.yaml")
    scenarios = multimeter["scenarios"]

    assert scenarios["voltage_static"]["name"] == "Voltage Static"
    assert scenarios["ascii_disconnect"]["name"] == "ASCII Disconnect"
    assert scenarios["ascii_response_delay_spike"]["name"] == "ASCII Response Delay Spike"
    assert scenarios["discharge_spike"]["name"] == "Discharge Spike"
