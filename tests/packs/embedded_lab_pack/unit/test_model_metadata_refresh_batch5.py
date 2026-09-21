# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path

import yaml

from tests.common.repo import repo_root


ROOT = repo_root()


def _load_yaml(relative_path: str) -> dict:
    path = ROOT / Path(relative_path)
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_power_analyzer_uses_typed_power_measurements() -> None:
    model = _load_yaml(
        "library/domains/lab/power_analyzer/rohde_schwarz/rohde_schwarz_hmc8015__scpi.yaml"
    )
    attributes = model["attributes"]

    assert attributes["voltage_rms_v"]["unit"] == "V"
    assert attributes["current_rms_a"]["unit"] == "A"
    assert attributes["apparent_power_va"]["unit"] == "VA"
    assert attributes["reactive_power_var"]["unit"] == "var"
    assert attributes["efficiency_pct"]["unit"] == "percent"
    assert all(action["description"] for action in model["actions"])


def test_power_supply_models_use_typed_channel_attributes() -> None:
    rigol = _load_yaml("library/domains/lab/power_supply/rigol/rigol_dp800__scpi.yaml")
    assert rigol["attributes"]["k__ch1_voltage_set_v"]["unit"] == "V"
    assert rigol["attributes"]["k__ch2_current_set_a"]["unit"] == "A"
    assert rigol["attributes"]["ch3_power_w"]["unit"] == "W"
    assert all(action["description"] for action in rigol["actions"])

    siglent = _load_yaml("library/domains/lab/power_supply/siglent/siglent_spd1000x__scpi.yaml")
    assert siglent["attributes"]["k__selected_output"]["type"] == "str"
    assert siglent["attributes"]["k__ch1_voltage_set_v"]["unit"] == "V"
    assert siglent["attributes"]["ch1_power_readback_w"]["unit"] == "W"
    assert all(action["description"] for action in siglent["actions"])

    rohde = _load_yaml(
        "library/domains/lab/power_supply/rohde_schwarz/rohde_schwarz_hmp4040__scpi.yaml"
    )
    assert rohde["attributes"]["k__selected_channel"]["type"] == "int"
    assert rohde["attributes"]["k__selected_voltage_set_v"]["unit"] == "V"
    assert rohde["attributes"]["ch4_current_a"]["unit"] == "A"
    assert rohde["attributes"]["selected_power_w"]["unit"] == "W"
    assert rohde["attributes"]["error_status"]["type"] == "str"
