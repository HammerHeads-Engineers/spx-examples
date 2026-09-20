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
    pack_index = _load_yaml("library/industries/smart_building_pack/MODELS.yaml")
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
        elif isinstance(bindings, dict):
            for binding in bindings.values():
                if isinstance(binding, dict):
                    yield binding
        for value in node.values():
            yield from _iter_bindings(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_bindings(item)


def test_smart_building_pack_models_use_typed_attributes_and_labeled_scenarios() -> None:
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


def test_smart_building_pack_representative_models_expose_modern_metadata() -> None:
    hvac = _load_yaml("library/domains/building/controller/generic/hvac_flexit_nordic__bacnet.yaml")
    assert hvac["attributes"]["room_thermal_mass_kwh_per_k"]["unit"] == "kWh/K"
    assert hvac["attributes"]["heater_load_pct"]["unit"] == "%"
    assert hvac["scenarios"]["heater_failure"]["display_name"] == "Heater failure"

    theronda = _load_yaml("library/domains/building/sensor/theben/theronda_p360__knx.yaml")
    assert theronda["attributes"]["k__brightness_ceiling_lux"]["unit"] == "lux"
    assert theronda["attributes"]["lighting_time_delay_s"]["unit"] == "s"
    assert theronda["scenarios"]["parallel_switching_pulse"]["display_name"] == "Parallel Switching Pulse"

    weather_feed = _load_yaml("library/domains/environment/feed/generic/weather_forecast__http.yaml")
    assert weather_feed["attributes"]["hourly_temperature_2m"]["type"] == "list"
    assert weather_feed["attributes"]["k__current_wind_speed"]["unit"] == "km/h"

    weather_gateway = _load_yaml(
        "library/domains/environment/gateway/wago_vaisala/weather_gateway_wago_pfc200__vaisala_wxt530__mqtt.yaml"
    )
    assert weather_gateway["attributes"]["k__wind_speed_ms"]["unit"] == "m/s"
    assert weather_gateway["attributes"]["_ha_discovery_outdoor_temperature_config"]["type"] == "str"
    assert weather_gateway["scenarios"]["Frontal passage sequence"]["display_name"] == (
        "Frontal passage sequence"
    )
