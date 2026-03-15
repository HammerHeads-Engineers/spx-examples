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
    / "power_supply"
    / "tdk_lambda"
    / "tdk_lambda_genesys_plus_g100_50__modbus.yaml"
)
MODEL_REL_PATH = (
    "library/domains/lab/power_supply/tdk_lambda/"
    "tdk_lambda_genesys_plus_g100_50__modbus.yaml"
)


def test_tdk_lambda_genesys_plus_g100_50_model_loads() -> None:
    doc = yaml.safe_load(MODEL_PATH.read_text(encoding="utf-8"))

    assert isinstance(doc, dict)
    assert doc.get("name") == "tdk_lambda_genesys_plus_g100_50__modbus"
    assert "attributes" in doc
    assert "actions" in doc
    assert "communication" in doc

    attributes = doc["attributes"]
    assert isinstance(attributes, dict)
    assert attributes.get("voltage_max_v") == 100.0
    assert attributes.get("current_max_a") == 50.0
    assert attributes.get("power_max_w") == 5000.0

    comm = doc["communication"]
    assert isinstance(comm, list) and comm
    modbus = comm[0].get("modbus_slave")
    assert isinstance(modbus, dict)
    assert modbus.get("port") == 5033

    mapping = modbus.get("mapping")
    assert isinstance(mapping, dict)
    assert "k__voltage_set_v" in mapping
    assert "k__current_limit_a" in mapping
    assert "power_actual_w" in mapping


def test_tdk_lambda_genesys_plus_g100_50_model_in_catalog() -> None:
    catalog_path = ROOT / "library" / "catalog" / "models.yaml"
    catalog = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    assert isinstance(catalog, dict)
    models = catalog.get("models")
    assert isinstance(models, list)

    matches = [
        m
        for m in models
        if isinstance(m, dict) and m.get("path") == MODEL_REL_PATH
    ]
    assert matches, "Model is missing from library/catalog/models.yaml"
    assert matches[0].get("domain") == "lab"
    assert matches[0].get("device_class") == "power_supply"
    assert matches[0].get("vendor") == "tdk_lambda"
