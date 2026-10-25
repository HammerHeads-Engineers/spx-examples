# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator

import yaml

from tests.common.repo import repo_root


ROOT = repo_root()


def _load_yaml(relative_path: str) -> dict[str, Any]:
    path = ROOT / Path(relative_path)
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _iter_pack_models() -> Iterator[tuple[str, dict[str, Any]]]:
    pack_index = _load_yaml("library/industries/industrial_iiot_pack/MODELS.yaml")
    catalog = _load_yaml("library/catalog/models.yaml")
    catalog_index = {entry["id"]: entry for entry in catalog["models"]}

    for entry in pack_index["models"]:
        yield entry["id"], _load_yaml(catalog_index[entry["id"]]["path"])


def _iter_bindings(node: Any) -> Iterator[dict[str, Any]]:
    if isinstance(node, dict):
        bindings = node.get("bindings")
        if isinstance(bindings, list):
            for binding in bindings:
                if isinstance(binding, dict):
                    yield binding
        for value in node.values():
            yield from _iter_bindings(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_bindings(item)


def test_industrial_pack_models_use_typed_attributes_and_labeled_scenarios() -> None:
    scalar_attrs: list[str] = []
    missing_display_names: list[str] = []
    unnamed_bindings: list[str] = []
    missing_name: list[str] = []
    missing_description: list[str] = []

    for model_id, model in _iter_pack_models():
        if not model.get("name"):
            missing_name.append(model_id)
        if not model.get("description"):
            missing_description.append(model_id)

        attributes = model.get("attributes") or {}
        for attr_name, attr_spec in attributes.items():
            if not isinstance(attr_spec, dict) or "type" not in attr_spec or "default" not in attr_spec:
                scalar_attrs.append(f"{model_id}:{attr_name}")

        for scenario_name, scenario in (model.get("scenarios") or {}).items():
            if isinstance(scenario, dict) and "display_name" not in scenario:
                missing_display_names.append(f"{model_id}:{scenario_name}")

        for binding in _iter_bindings(model.get("communication") or []):
            if "name" not in binding:
                unnamed_bindings.append(model_id)

    assert scalar_attrs == []
    assert missing_display_names == []
    assert unnamed_bindings == []
    assert missing_name == []
    assert missing_description == []


def test_industrial_pack_representative_models_expose_modern_metadata() -> None:
    abb_m1m = _load_yaml(
        "library/domains/energy/power_meter/abb/abb_m1m_power_meter__modbus.yaml"
    )
    assert abb_m1m["attributes"]["k__load_kw"]["unit"] == "kW"
    assert abb_m1m["attributes"]["frequency_droop_per_kw"]["unit"] == "Hz/kW"
    assert abb_m1m["scenarios"]["low_power_factor"]["display_name"] == "Low Power Factor"

    eurotherm_3504 = _load_yaml(
        "library/domains/industrial/controller/eurotherm/eurotherm_3504__modbus.yaml"
    )
    assert eurotherm_3504["meta_parameters"]["modbus_port"]["default"] == 5027
    assert eurotherm_3504["attributes"]["control_out_pct"]["unit"] == "percent"
    assert eurotherm_3504["scenarios"]["manual_hold_40"]["display_name"] == "Manual Hold 40%"

    thermal_advanced = _load_yaml(
        "library/domains/industrial/controller/generic/thermal_controller_advanced.yaml"
    )
    assert thermal_advanced["name"] == "thermal_controller_advanced"
    assert thermal_advanced["attributes"]["temperature"]["unit"] == "degC"
    assert thermal_advanced["scenarios"]["heat_treat_sequence_profile"]["display_name"] == (
        "Heat Treat Sequence (Profile)"
    )

    process_cell = _load_yaml(
        "library/domains/industrial/process_cell/generic/process_cell__opcua.yaml"
    )
    assert process_cell["attributes"]["flow_rate_lpm"]["unit"] == "L/min"
    assert process_cell["scenarios"]["maintenance_idle"]["display_name"] == "Maintenance Idle"

    vision_station = _load_yaml(
        "library/domains/industrial/station/generic/vision_quality_station__http.yaml"
    )
    assert vision_station["meta_parameters"]["http_port"]["default"] == 8093
    assert vision_station["attributes"]["ok_count"]["unit"] == "count"
    assert vision_station["scenarios"]["defect_burst"]["display_name"] == "Defect Burst"
