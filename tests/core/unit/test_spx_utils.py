# SPDX-License-Identifier: MIT

from __future__ import annotations

import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import pytest

from tests.common import spx_utils


@dataclass
class _FakeModel:
    definition: Dict[str, Any]


class _FakeModels:
    def __init__(self) -> None:
        self._store: Dict[str, _FakeModel] = {}

    def __getitem__(self, key: str) -> _FakeModel:
        return self._store[key]

    def __setitem__(self, key: str, value: Dict[str, Any]) -> None:
        self._store[key] = _FakeModel(definition=value)


class _FakeInstance:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []
        self._doc: dict[str, Any] = {"state": "stopped"}
        self.model_id: Optional[str] = None

    def stop(self) -> None:
        self.calls.append(("stop", None))

    def reset(self) -> None:
        self.calls.append(("reset", None))

    def start(self) -> None:
        self.calls.append(("start", None))
        self._doc["state"] = "running"

    def put_attr(self, path: str, value: Any) -> None:
        self.calls.append(("put_attr", (path, value)))

    def get(self) -> dict[str, Any]:
        return dict(self._doc)


class _FakeInstances:
    def __init__(self) -> None:
        self._store: Dict[str, _FakeInstance] = {}
        self.generate_calls: list[Dict[str, Any]] = []

    def __getitem__(self, key: str) -> _FakeInstance:
        return self._store[key]

    def __setitem__(self, key: str, model_key: str) -> None:  # noqa: ARG002
        self._store[key] = _FakeInstance()

    def __delitem__(self, key: str) -> None:
        del self._store[key]

    def generate(
        self,
        *,
        template: str,  # noqa: ARG002
        count: int,  # noqa: ARG002
        name: str,
        parameters: Dict[str, Any],
    ) -> None:
        self.generate_calls.append(
            {
                "template": template,
                "count": count,
                "name": name,
                "parameters": parameters,
            }
        )
        self._store[name] = _FakeInstance()


class _FakeClient(dict):
    def __init__(self) -> None:
        super().__init__()
        self["models"] = _FakeModels()
        self["instances"] = _FakeInstances()


class _FakeSPX:
    def __init__(self, client: Optional[_FakeClient] = None) -> None:
        self._client = client or _FakeClient()

    def init(self, *, address: str, product_key: str) -> _FakeClient:  # noqa: ARG002
        return self._client


def _write_minimal_model(path: Path) -> None:
    path.write_text(
        "name: example\nattributes:\n  value: 1\n",
        encoding="utf-8",
    )


def test_resolve_model_path_uses_catalog_entry_for_moved_model(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    catalog_dir = repo_root / "library" / "catalog"
    model_dir = repo_root / "library" / "domains" / "environment" / "sensor" / "generic"
    legacy_path = (
        repo_root
        / "library"
        / "domains"
        / "iot"
        / "generic"
        / "environment_sensor__mqtt.yaml"
    )
    model_path = model_dir / "environment_sensor__mqtt.yaml"

    catalog_dir.mkdir(parents=True)
    model_dir.mkdir(parents=True)
    _write_minimal_model(model_path)
    (catalog_dir / "models.yaml").write_text(
        "\n".join(
            [
                "models:",
                "- id: Env.EnvSensor.Mqtt",
                "  path: library/domains/environment/sensor/generic/environment_sensor__mqtt.yaml",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    resolved = spx_utils.resolve_model_path(
        legacy_path,
        model_key="Env.EnvSensor.Mqtt",
        repo_root=repo_root,
    )

    assert resolved == model_path


def test_load_model_definition_falls_back_to_unique_catalog_filename(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    catalog_dir = repo_root / "library" / "catalog"
    model_dir = repo_root / "library" / "domains" / "lab" / "instrument" / "siglent"
    legacy_path = (
        repo_root
        / "library"
        / "domains"
        / "measurement_instruments"
        / "siglent"
        / "siglent_sdm3055__scpi.yaml"
    )
    model_path = model_dir / "siglent_sdm3055__scpi.yaml"

    catalog_dir.mkdir(parents=True)
    model_dir.mkdir(parents=True)
    _write_minimal_model(model_path)
    (catalog_dir / "models.yaml").write_text(
        "\n".join(
            [
                "models:",
                "- id: Lab.Multimeter.SiglentSdm3055.Scpi",
                "  path: library/domains/lab/instrument/siglent/siglent_sdm3055__scpi.yaml",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    model_def = spx_utils.load_model_definition(
        legacy_path,
        model_key=None,
        repo_root=repo_root,
    )

    assert model_def["name"] == "example"


def test_resolve_model_path_raises_when_no_catalog_replacement_exists(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    catalog_dir = repo_root / "library" / "catalog"
    catalog_dir.mkdir(parents=True)
    (catalog_dir / "models.yaml").write_text("models: []\n", encoding="utf-8")

    missing_path = (
        repo_root / "library" / "domains" / "iot" / "generic" / "missing.yaml"
    )

    with pytest.raises(FileNotFoundError, match="no replacement was found"):
        spx_utils.resolve_model_path(missing_path, repo_root=repo_root)


def test_ensure_instance_applies_overrides_after_reset_on_create() -> None:
    client = _FakeClient()
    instance = spx_utils.ensure_instance(
        client,
        "inst",
        "model",
        overrides={"communication/http_endpoint/port": 9999},
        recreate=True,
        reset_on_create=True,
        start_on_create=False,
    )

    calls = [name for name, _payload in instance.calls]
    assert "reset" in calls
    assert "put_attr" in calls
    assert calls.index("reset") < calls.index("put_attr")


def test_bootstrap_model_instance_resets_and_applies_overrides_after_reset(
    tmp_path: Path,
) -> None:
    model_path = tmp_path / "model.yaml"
    _write_minimal_model(model_path)

    spx = _FakeSPX()

    _, instance, model_changed = spx_utils.bootstrap_model_instance(
        spx,
        product_key="TEST",
        base_url="http://example",
        model_path=model_path,
        model_key="model_key",
        instance_key="instance_key",
        attribute_overrides={"communication/http_endpoint/port": 8099},
    )
    assert model_changed is True

    names = [name for name, _payload in instance.calls]
    assert names.count("reset") == 1
    assert "put_attr" in names
    assert names.index("reset") < names.index("put_attr")
    assert names.index("put_attr") < names.index("start")

    # Second call should still reset/start the instance even if the model is unchanged.
    _, instance_2, model_changed_2 = spx_utils.bootstrap_model_instance(
        spx,
        product_key="TEST",
        base_url="http://example",
        model_path=model_path,
        model_key="model_key",
        instance_key="instance_key",
        attribute_overrides={"communication/http_endpoint/port": 8099},
    )
    assert instance_2 is instance
    assert model_changed_2 is False

    names_after = [name for name, _payload in instance.calls]
    assert names_after.count("reset") == 2
    assert names_after.count("start") == 2


def test_ensure_instance_uses_generate_for_meta_parameter_defaults() -> None:
    client = _FakeClient()
    model_def = {
        "meta_parameters": {
            "modbus_port": {"type": "int", "default": 5023},
            "modbus_unit_id": {"type": "int", "default": 1},
        }
    }

    instance = spx_utils.ensure_instance(
        client,
        "inst",
        "model",
        model_def=model_def,
        recreate=True,
        ensure_running=False,
        reset_on_create=False,
        start_on_create=False,
    )

    assert instance is client["instances"]["inst"]
    assert client["instances"].generate_calls == [
        {
            "template": "model",
            "count": 1,
            "name": "inst",
            "parameters": {
                "modbus_port": {"cycle": [5023]},
                "modbus_unit_id": {"cycle": [1]},
            },
        }
    ]


def test_ensure_instance_uses_generate_for_meta_parameter_overrides() -> None:
    client = _FakeClient()
    model_def = {
        "meta_parameters": {
            "modbus_port": {"type": "int", "default": 5023},
            "modbus_unit_id": {"type": "int", "default": 1},
        }
    }

    instance = spx_utils.ensure_instance(
        client,
        "inst",
        "model",
        model_def=model_def,
        meta_parameters={"modbus_port": 5601, "modbus_unit_id": 11},
        recreate=True,
        ensure_running=False,
        reset_on_create=False,
        start_on_create=False,
    )

    assert instance is client["instances"]["inst"]
    assert client["instances"].generate_calls == [
        {
            "template": "model",
            "count": 1,
            "name": "inst",
            "parameters": {
                "modbus_port": {"cycle": [5601]},
                "modbus_unit_id": {"cycle": [11]},
            },
        }
    ]


def test_ensure_instance_errors_when_required_meta_default_missing() -> None:
    client = _FakeClient()
    model_def = {
        "meta_parameters": {
            "modbus_port": {"type": "int", "required": True},
        }
    }

    with pytest.raises(
        RuntimeError, match="Missing defaults for required meta_parameters"
    ):
        spx_utils.ensure_instance(
            client,
            "inst",
            "model",
            model_def=model_def,
            recreate=True,
            ensure_running=False,
            reset_on_create=False,
            start_on_create=False,
        )


def test_ensure_instance_errors_when_unknown_meta_override_is_provided() -> None:
    client = _FakeClient()
    model_def = {
        "meta_parameters": {
            "modbus_port": {"type": "int", "default": 5023},
        }
    }

    with pytest.raises(RuntimeError, match="Unknown meta_parameters provided"):
        spx_utils.ensure_instance(
            client,
            "inst",
            "model",
            model_def=model_def,
            meta_parameters={"modbus_unit_id": 11},
            recreate=True,
            ensure_running=False,
            reset_on_create=False,
            start_on_create=False,
        )


def test_require_existing_instance_skips_when_missing() -> None:
    client = _FakeClient()
    with pytest.raises(unittest.SkipTest):
        spx_utils.require_existing_instance(client, "missing")


def test_require_existing_instance_starts_when_not_running() -> None:
    client = _FakeClient()
    client["instances"]["inst"] = "model"
    instance = client["instances"]["inst"]
    instance._doc["state"] = "stopped"

    resolved = spx_utils.require_existing_instance(client, "inst", ensure_running=True)
    assert resolved is instance
    assert any(name == "start" for name, _payload in instance.calls)


def test_require_existing_instance_validates_model_id() -> None:
    client = _FakeClient()
    client["instances"]["inst"] = "model"
    instance = client["instances"]["inst"]
    instance.model_id = "Actual.Model"
    instance._doc["state"] = "running"

    with pytest.raises(AssertionError):
        spx_utils.require_existing_instance(
            client,
            "inst",
            expected_model_id="Expected.Model",
            ensure_running=False,
        )
