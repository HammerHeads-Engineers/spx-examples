# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path

import yaml

from tests.common.repo import repo_root


ROOT = repo_root()


def _load_yaml(relative_path: str) -> dict:
    path = ROOT / Path(relative_path)
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_embedded_lab_digital_multimeter_scpi_models_use_named_mappings() -> None:
    model_paths = [
        "library/domains/lab/digital_multimeter/generic/digital_multimeter__scpi.yaml",
        "library/domains/lab/digital_multimeter/siglent/siglent_sdm3055__scpi.yaml",
        "library/domains/lab/digital_multimeter/tektronix/tektronix_dmm4050__scpi.yaml",
        "library/domains/lab/digital_multimeter/rohde_schwarz/rohde_schwarz_hmc8012__scpi.yaml",
    ]

    for relative_path in model_paths:
        doc = _load_yaml(relative_path)
        mappings = doc["communication"][0]["ascii"]["mappings"]
        names: list[str] = []

        for command, spec in mappings.items():
            assert isinstance(spec, dict), f"{relative_path}:{command} must use dict-form mapping"
            assert "name" in spec, f"{relative_path}:{command} is missing explicit mapping name"
            names.append(spec["name"])

        assert len(names) == len(set(names)), f"{relative_path} has duplicate mapping names"


def test_embedded_lab_digital_multimeter_scpi_models_expose_configurable_ascii_ports() -> None:
    model_paths = [
        "library/domains/lab/digital_multimeter/generic/digital_multimeter__scpi.yaml",
        "library/domains/lab/digital_multimeter/siglent/siglent_sdm3055__scpi.yaml",
        "library/domains/lab/digital_multimeter/tektronix/tektronix_dmm4050__scpi.yaml",
        "library/domains/lab/digital_multimeter/rohde_schwarz/rohde_schwarz_hmc8012__scpi.yaml",
    ]

    for relative_path in model_paths:
        doc = _load_yaml(relative_path)
        meta_parameters = doc["meta_parameters"]
        ascii = doc["communication"][0]["ascii"]

        assert meta_parameters["ascii_port"]["type"] == "int"
        assert meta_parameters["ascii_port"]["default"] == 0
        assert ascii["port"] == "$param(ascii_port)"


def test_rohde_schwarz_hmc8012_scpi_uses_descriptive_mapping_names() -> None:
    model = _load_yaml(
        "library/domains/lab/digital_multimeter/rohde_schwarz/rohde_schwarz_hmc8012__scpi.yaml"
    )
    mappings = model["communication"][0]["ascii"]["mappings"]

    assert mappings["*IDN?"]["name"] == "query_idn"
    assert mappings["CONF:CURR:DC {range}"]["name"] == "configure_current_dc_range"
    assert mappings["MEAS:FREQ?"]["name"] == "query_measurement_frequency"
    assert mappings["SYST:ERR?"]["name"] == "query_system_error"
