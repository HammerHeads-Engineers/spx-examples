# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path

import yaml

from tests.common.repo import repo_root


ROOT = repo_root()


def _load_yaml(relative_path: str) -> dict:
    path = ROOT / Path(relative_path)
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_embedded_lab_oscilloscope_scpi_mappings_are_named() -> None:
    pack_index = _load_yaml("library/industries/embedded_lab_pack/MODELS.yaml")
    catalog = _load_yaml("library/catalog/models.yaml")
    model_index = {entry["id"]: entry for entry in catalog["models"]}

    oscilloscope_ids = [
        entry["id"]
        for entry in pack_index["models"]
        if entry["id"].startswith("Lab.Oscilloscope.") and entry["id"].endswith(".Scpi")
    ]

    assert oscilloscope_ids

    for model_id in oscilloscope_ids:
        model = _load_yaml(model_index[model_id]["path"])
        communication = model["communication"]
        ascii_protocol = communication[0]["ascii"]
        mappings = ascii_protocol["mappings"]

        names = []
        for command, spec in mappings.items():
            assert isinstance(spec, dict), f"{model_id}:{command} must use dict-form mapping"
            assert "name" in spec, f"{model_id}:{command} is missing explicit mapping name"
            names.append(spec["name"])

        assert len(names) == len(set(names)), f"{model_id} has duplicate mapping names"


def test_keysight_1000x_scpi_uses_descriptive_mapping_names() -> None:
    model = _load_yaml(
        "library/domains/lab/oscilloscope/keysight/keysight_infiniivision_1000x__scpi.yaml"
    )
    mappings = model["communication"][0]["ascii"]["mappings"]

    assert mappings["*IDN?"]["name"] == "query_idn"
    assert mappings[":MEASure:VPP?"]["name"] == "query_channel_1_vpp"
    assert mappings[":MEASure:VAVerage?"]["name"] == "query_channel_1_vavg"
    assert mappings[":TIMebase:SCALe {scale}"]["name"] == "set_timebase_scale"
