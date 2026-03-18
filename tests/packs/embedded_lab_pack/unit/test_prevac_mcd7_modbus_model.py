# SPDX-License-Identifier: MIT

from __future__ import annotations

import yaml

from tests.common.repo import repo_root


ROOT = repo_root()
MODEL_PATH = (
    ROOT
    / "library"
    / "domains"
    / "lab"
    / "detector"
    / "prevac"
    / "prevac_mcd7__modbus.yaml"
)
MODEL_REL_PATH = (
    "library/domains/lab/detector/prevac/prevac_mcd7__modbus.yaml"
)


def test_prevac_mcd7_modbus_model_loads() -> None:
    doc = yaml.safe_load(MODEL_PATH.read_text(encoding="utf-8"))

    assert isinstance(doc, dict)
    assert doc.get("name") == "prevac_mcd7__modbus"
    description = str(doc.get("description", "")).lower()
    assert "prevac mcd7" in description
    assert "multichanneltron detector" in description

    attributes = doc.get("attributes")
    assert isinstance(attributes, dict)
    assert attributes["measure_done"]["default"] == 1
    assert attributes["measure_start"]["default"] == 0
    assert attributes["dwell_time"] == 100

    communication = doc.get("communication")
    assert isinstance(communication, list) and communication
    modbus = communication[0].get("modbus_slave")
    assert isinstance(modbus, dict)

    mapping = modbus.get("mapping")
    assert isinstance(mapping, dict)
    assert mapping["measure_done"]["address"] == [0, 0]
    assert mapping["ch_7_impulse"]["address"] == [16, 17]
    assert mapping["ch_7_comparator"]["address"] == [24, 24]

    scenarios = doc.get("scenarios")
    assert isinstance(scenarios, dict)
    assert scenarios["modbus_disconnect"]["display_name"] == "Modbus Disconnect"
    assert scenarios["channel_3_dropout"]["display_name"] == "Channel 3 Dropout"


def test_prevac_mcd7_modbus_model_in_catalog() -> None:
    catalog_path = ROOT / "library" / "catalog" / "models.yaml"
    catalog = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))

    assert isinstance(catalog, dict)
    models = catalog.get("models")
    assert isinstance(models, list)

    matches = [
        model
        for model in models
        if isinstance(model, dict) and model.get("path") == MODEL_REL_PATH
    ]
    assert matches, "Model is missing from library/catalog/models.yaml"

    entry = matches[0]
    assert entry.get("id") == "Lab.Detector.PrevacMCD7.Modbus"
    assert entry.get("domain") == "lab"
    assert entry.get("device_class") == "detector"
    assert entry.get("vendor") == "prevac"
