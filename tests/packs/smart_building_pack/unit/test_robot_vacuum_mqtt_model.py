# SPDX-License-Identifier: MIT

from __future__ import annotations

import yaml

from tests.common.repo import repo_root


ROOT = repo_root()
MODEL_PATH = (
    ROOT
    / "library"
    / "domains"
    / "building"
    / "actuator"
    / "generic"
    / "robot_vacuum__mqtt.yaml"
)
MODEL_REL_PATH = "library/domains/building/actuator/generic/robot_vacuum__mqtt.yaml"


def test_robot_vacuum_mqtt_model_loads() -> None:
    doc = yaml.safe_load(MODEL_PATH.read_text(encoding="utf-8"))

    assert isinstance(doc, dict)
    assert doc.get("name") == "robot_vacuum__mqtt"
    assert "attributes" in doc
    assert "actions" in doc
    assert "communication" in doc
    assert "scenarios" in doc

    attributes = doc["attributes"]
    assert isinstance(attributes, dict)
    assert attributes.get("docked") == 1
    assert attributes.get("battery_percent") == 100.0
    assert attributes.get("suction_level_percent") == 70.0

    comm = doc["communication"]
    assert isinstance(comm, list) and comm
    mqtt = comm[0].get("mqtt")
    assert isinstance(mqtt, dict)
    assert mqtt.get("topic_prefix") == "spx/examples/robot_vacuum"

    bindings = mqtt.get("bindings")
    assert isinstance(bindings, list) and bindings
    topics = {binding.get("topic") for binding in bindings if isinstance(binding, dict)}
    assert "telemetry/status" in topics
    assert "command/desired_cleaning" in topics
    assert "command/dock_request" in topics

    scenarios = doc["scenarios"]
    assert isinstance(scenarios, dict)
    assert "start_cleaning" in scenarios
    assert "return_to_dock" in scenarios
    assert "bin_full_alarm" in scenarios


def test_robot_vacuum_mqtt_model_in_catalog() -> None:
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
    assert entry.get("id") == "Building.RobotVacuum.Mqtt"
    assert entry.get("domain") == "building"
    assert entry.get("device_class") == "actuator"
    assert entry.get("vendor") == "generic"
    assert entry.get("packages") == ["smart_building_pack"]
    assert entry.get("profiles") == []
