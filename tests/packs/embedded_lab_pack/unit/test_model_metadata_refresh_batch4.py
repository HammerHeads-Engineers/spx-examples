# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path

import yaml

from tests.common.repo import repo_root


ROOT = repo_root()


def _load_yaml(relative_path: str) -> dict:
    path = ROOT / Path(relative_path)
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_oscilloscope_models_define_typed_measurement_attributes() -> None:
    keysight_scope = _load_yaml(
        "library/domains/lab/oscilloscope/keysight/keysight_infiniivision_1000x__scpi.yaml"
    )
    assert keysight_scope["attributes"]["k__channel_1_scale_v"]["unit"] == "V"
    assert keysight_scope["attributes"]["k__timebase_scale_s"]["unit"] == "s"
    assert keysight_scope["attributes"]["frequency_hz"]["unit"] == "Hz"
    assert keysight_scope["attributes"]["last_error"]["type"] == "str"

    for relative_path in [
        "library/domains/lab/oscilloscope/rigol/rigol_ds1000z__scpi.yaml",
        "library/domains/lab/oscilloscope/rigol/rigol_mso5000__scpi.yaml",
        "library/domains/lab/oscilloscope/rohde_schwarz/rohde_schwarz_hmo1002__scpi.yaml",
        "library/domains/lab/oscilloscope/siglent/siglent_sds1000x_e__scpi.yaml",
        "library/domains/lab/oscilloscope/siglent/siglent_sds2000x_hd__scpi.yaml",
        "library/domains/lab/oscilloscope/tektronix/tektronix_mdo3000__scpi.yaml",
    ]:
        model = _load_yaml(relative_path)
        attributes = model["attributes"]

        assert attributes["channel1_vpp_v"]["unit"] == "V"
        assert attributes["channel1_vrms_v"]["unit"] == "V"
        assert attributes["channel1_freq_hz"]["unit"] == "Hz"
        assert attributes["channel1_period_s"]["unit"] == "s"
        assert all(action["description"] for action in model["actions"])


def test_scope_scenarios_use_human_readable_display_names() -> None:
    for relative_path in [
        "library/domains/lab/oscilloscope/rigol/rigol_ds1000z__scpi.yaml",
        "library/domains/lab/oscilloscope/rigol/rigol_mso5000__scpi.yaml",
        "library/domains/lab/oscilloscope/siglent/siglent_sds1000x_e__scpi.yaml",
        "library/domains/lab/oscilloscope/siglent/siglent_sds2000x_hd__scpi.yaml",
    ]:
        model = _load_yaml(relative_path)
        assert model["scenarios"]["amplitude_sweep"]["display_name"] == "Amplitude Sweep"


def test_spectrum_analyzer_model_uses_typed_attributes() -> None:
    model = _load_yaml("library/domains/lab/spectrum_analyzer/siglent/siglent_ssa3000x__scpi.yaml")
    attributes = model["attributes"]

    assert attributes["k__center_frequency_hz"]["unit"] == "Hz"
    assert attributes["k__span_hz"]["unit"] == "Hz"
    assert attributes["k__reference_level_dbm"]["unit"] == "dBm"
    assert attributes["marker_1_level_dbm"]["unit"] == "dBm"
