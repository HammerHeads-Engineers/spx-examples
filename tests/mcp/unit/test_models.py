# SPDX-License-Identifier: MIT

from pathlib import Path
import builtins
from dataclasses import dataclass
from typing import Any, Dict

import pytest

from spx_mcp.backend.catalog import RepoCatalog
from spx_mcp.backend.models import (
    delete_model_scenario,
    ensure_model_registered,
    extract_model_definition,
    get_registered_model_definition,
    get_model_scenario,
    list_model_scenarios,
    load_model_definition,
    register_model_from_catalog,
    upsert_model_scenario,
    validate_model_path,
)


def test_validate_model_path_reports_missing_attributes(tmp_path: Path) -> None:
    model_path = tmp_path / "broken_model.yaml"
    model_path.write_text("name: broken_model\n", encoding="utf-8")

    result = validate_model_path(model_path)

    assert result["ok"] is False
    assert any("attributes" in error for error in result["errors"])


def test_repo_model_scenario_helpers_round_trip_yaml(tmp_path: Path) -> None:
    catalog = _make_catalog(tmp_path)

    created = upsert_model_scenario(
        catalog,
        "sensor",
        "pm10_rise_hold_fall",
        {
            "duration": 12.0,
            "conditions": [
                {
                    "if": "$attr(timer.time) < 5.0",
                    "actions": [
                        {
                            "function": "$in(pm10)",
                            "params": {"target": 90.0},
                            "call": "target",
                        }
                    ],
                }
            ],
        },
    )

    listed = list_model_scenarios(catalog, "sensor")
    fetched = get_model_scenario(catalog, "sensor", "pm10_rise_hold_fall")

    assert created["changed"] is True
    assert created["replaced"] is False
    assert created["validation"]["ok"] is True
    assert listed["scenario_names"] == ["pm10_rise_hold_fall"]
    assert fetched["scenario"]["duration"] == 12.0
    assert "pm10_rise_hold_fall:" in catalog.get_model_path("sensor").read_text(encoding="utf-8")


def test_upsert_model_scenario_rejects_duplicate_without_replace(tmp_path: Path) -> None:
    catalog = _make_catalog(tmp_path)

    upsert_model_scenario(
        catalog,
        "sensor",
        "demo",
        {"duration": 1.0},
    )

    with pytest.raises(ValueError, match="already exists"):
        upsert_model_scenario(
            catalog,
            "sensor",
            "demo",
            {"duration": 2.0},
            replace=False,
        )


def test_delete_model_scenario_removes_definition(tmp_path: Path) -> None:
    catalog = _make_catalog(tmp_path)
    upsert_model_scenario(
        catalog,
        "sensor",
        "demo",
        {"duration": 1.0},
    )

    payload = delete_model_scenario(catalog, "sensor", "demo")

    assert payload["deleted"] is True
    assert list_model_scenarios(catalog, "sensor")["scenario_names"] == []


def test_get_model_scenario_rejects_missing_name(tmp_path: Path) -> None:
    catalog = _make_catalog(tmp_path)

    with pytest.raises(ValueError, match="not found"):
        get_model_scenario(catalog, "sensor", "missing")


@dataclass
class _FakeModelNode:
    definition: Dict[str, Any]


class _FakeModels:
    def __init__(self) -> None:
        self._store: Dict[str, _FakeModelNode] = {}

    def __getitem__(self, key: str) -> _FakeModelNode:
        return self._store[key]

    def __setitem__(self, key: str, value: Dict[str, Any]) -> None:
        self._store[key] = _FakeModelNode(definition=value)


class _FakeClient(dict):
    def __init__(self) -> None:
        super().__init__()
        self["models"] = _FakeModels()


def test_load_model_definition_loads_mapping_from_yaml(tmp_path: Path) -> None:
    model_path = tmp_path / "model.yaml"
    model_path.write_text("name: demo\nattributes:\n  value: 1\n", encoding="utf-8")

    payload = load_model_definition(model_path)

    assert payload["name"] == "demo"


def test_ensure_model_registered_is_idempotent_for_same_definition() -> None:
    client = _FakeClient()
    definition = {"name": "demo", "attributes": {"value": 1}}

    changed_first = ensure_model_registered(client, "demo", definition)
    changed_second = ensure_model_registered(client, "demo", definition)

    assert changed_first is True
    assert changed_second is False


def test_register_model_from_catalog_does_not_require_spx_python_helpers(
    tmp_path: Path,
    monkeypatch,
) -> None:
    catalog = _make_catalog(tmp_path)
    client = _FakeClient()
    original_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "spx_python.helpers" or name.startswith("spx_python.helpers."):
            raise AssertionError("spx_python.helpers should not be imported by runtime MCP")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    payload = register_model_from_catalog(client, catalog, "sensor")

    assert payload["changed"] is True
    assert client["models"]._store["sensor"].definition["name"] == "sensor"


def test_get_registered_model_definition_reads_definition_attribute() -> None:
    client = _FakeClient()
    client["models"]["demo"] = {"name": "demo", "attributes": {"value": 1}}

    definition = get_registered_model_definition(client["models"], "demo")

    assert definition == {"name": "demo", "attributes": {"value": 1}}


def test_extract_model_definition_reads_nested_definition_mapping() -> None:
    definition = extract_model_definition(
        {"definition": {"name": "demo", "attributes": {"value": 1}}}
    )

    assert definition == {"name": "demo", "attributes": {"value": 1}}


def _make_catalog(tmp_path: Path) -> RepoCatalog:
    catalog_dir = tmp_path / "library" / "catalog"
    profiles_dir = tmp_path / "profiles" / "test_pack"
    domains_dir = tmp_path / "library" / "domains" / "environment" / "sensor" / "generic"
    industries_dir = tmp_path / "library" / "industries" / "test_pack"
    catalog_dir.mkdir(parents=True)
    profiles_dir.mkdir(parents=True)
    domains_dir.mkdir(parents=True)
    industries_dir.mkdir(parents=True)

    (domains_dir / "sensor.yaml").write_text(
        "\n".join(
            [
                "name: sensor",
                "description: Demo sensor",
                "attributes:",
                "  temperature: 20",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (catalog_dir / "domains.yaml").write_text(
        "domains:\n  - id: environment\n    name: Environment\n    description: Env\n    path: library/domains/environment\n",
        encoding="utf-8",
    )
    (catalog_dir / "services.yaml").write_text(
        "services: []\n",
        encoding="utf-8",
    )
    (catalog_dir / "industries.yaml").write_text(
        "industries:\n  - id: test_pack\n    name: Test Pack\n    description: Example\n    protocols: [mqtt]\n    services: []\n    profiles:\n      - profiles/test_pack/test_profile.yaml\n    path: library/industries/test_pack\n",
        encoding="utf-8",
    )
    (catalog_dir / "models.yaml").write_text(
        "\n".join(
            [
                "models:",
                "  - id: sensor",
                "    name: sensor",
                "    path: library/domains/environment/sensor/generic/sensor.yaml",
                "    domain: environment",
                "    domain_group: environment",
                "    device_class: sensor",
                "    vendor: generic",
                "    protocols: [mqtt]",
                "    services: []",
                "    packages: [test_pack]",
                "    profiles: [test_profile]",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (profiles_dir / "test_profile.yaml").write_text(
        "name: test_profile\ndescription: Example profile\nmodels:\n  - library/domains/environment/sensor/generic/sensor.yaml\nservices: []\n",
        encoding="utf-8",
    )
    (industries_dir / "README.md").write_text("# Test Pack\n", encoding="utf-8")
    (industries_dir / "SPEC.md").write_text("# Spec\n", encoding="utf-8")
    (industries_dir / "MODELS.yaml").write_text("models: []\n", encoding="utf-8")

    return RepoCatalog(tmp_path)
