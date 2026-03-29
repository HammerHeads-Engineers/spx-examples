# SPDX-License-Identifier: MIT

import builtins
from pathlib import Path

import pytest

from spx_mcp.backend import bootstrap
from spx_mcp.backend.bootstrap import meta_parameter_defaults


def test_meta_parameter_defaults_uses_defaults_and_overrides() -> None:
    payload = {
        "meta_parameters": {
            "port": {"type": "int", "default": 5020},
            "zone": {"type": "str", "required": True},
        }
    }

    params, missing = meta_parameter_defaults(payload, overrides={"zone": "north"})

    assert params["port"] == {"cycle": [5020]}
    assert params["zone"] == {"cycle": ["north"]}
    assert missing == []


def test_meta_parameter_defaults_rejects_unknown_overrides() -> None:
    payload = {"meta_parameters": {"port": {"type": "int", "default": 1}}}

    with pytest.raises(ValueError):
        meta_parameter_defaults(payload, overrides={"missing": 2})


def test_register_model_and_ensure_instance_chains_model_and_instance(monkeypatch) -> None:
    class DummyCatalog:
        def get_model_path(self, model_id: str) -> str:
            return f"/tmp/{model_id}.yaml"

    monkeypatch.setattr(
        bootstrap,
        "register_model_from_catalog",
        lambda client, catalog, model_id: {"model_id": model_id, "changed": True},
    )
    monkeypatch.setattr(
        bootstrap,
        "load_model_definition",
        lambda model_path: {"name": "demo.model", "attributes": {"value": 1}},
    )

    def fake_ensure_instance(client, **kwargs):
        class DummyInstance:
            state = "RUNNING"

            def get(self):
                return {
                    "state": "RUNNING",
                    "model_id": "demo.model",
                    "communication": {
                        "modbus_tcp": {
                            "host": "127.0.0.1",
                            "port": 1502,
                            "unit_id": 3,
                        }
                    },
                }

        assert kwargs["model_id"] == "demo.model"
        assert kwargs["instance_key"] == "demo_instance"
        assert kwargs["model_path"] == "/tmp/demo.model.yaml"
        assert kwargs["recreate"] is True
        assert kwargs["ensure_running"] is True
        assert kwargs["start_on_create"] is True
        return DummyInstance()

    monkeypatch.setattr(bootstrap, "ensure_instance", fake_ensure_instance)

    payload = bootstrap.register_model_and_ensure_instance(
        object(),
        DummyCatalog(),
        model_id="demo.model",
        instance_key="demo_instance",
        start=True,
        recreate=True,
    )

    assert payload == {
        "model": {"model_id": "demo.model", "changed": True},
        "instance": {
            "instance_key": "demo_instance",
            "model_id": "demo.model",
            "state": "RUNNING",
            "endpoint_details": {
                "modbus_tcp": {
                    "host": "127.0.0.1",
                    "port": 1502,
                    "unit_id": 3,
                }
            },
        },
    }


class _FakeInstance:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self._doc = {
            "state": "STOPPED",
            "model_id": "demo.model",
            "communication": {
                "modbus_slave": {
                    "attr": {
                        "port": {"value": 5027},
                        "unit_id": {"value": 11},
                    }
                }
            },
        }

    @property
    def state(self) -> str:
        return self._doc["state"]

    def stop(self) -> None:
        self.calls.append(("stop", None))

    def reset(self) -> None:
        self.calls.append(("reset", None))

    def start(self) -> None:
        self.calls.append(("start", None))
        self._doc["state"] = "RUNNING"

    def put_attr(self, path: str, value) -> None:
        self.calls.append(("put_attr", (path, value)))

    def get(self):
        return dict(self._doc)


class _FakeInstances:
    def __init__(self) -> None:
        self._store = {}
        self.generate_calls = []

    def __getitem__(self, key: str):
        return self._store[key]

    def __setitem__(self, key: str, model_id: str) -> None:
        instance = _FakeInstance()
        instance._doc["model_id"] = model_id
        self._store[key] = instance

    def __delitem__(self, key: str) -> None:
        del self._store[key]

    def generate(self, *, template: str, count: int, name: str, parameters):  # noqa: ANN001
        self.generate_calls.append(
            {
                "template": template,
                "count": count,
                "name": name,
                "parameters": parameters,
            }
        )
        self[name] = template


class _FakeClient(dict):
    def __init__(self) -> None:
        super().__init__()
        self["instances"] = _FakeInstances()


def test_ensure_instance_bootstraps_direct_instance_without_helpers(tmp_path: Path, monkeypatch) -> None:
    model_path = tmp_path / "model.yaml"
    model_path.write_text(
        "name: demo\nattributes:\n  value: 1\n",
        encoding="utf-8",
    )
    client = _FakeClient()

    instance = bootstrap.ensure_instance(
        client,
        model_id="demo.model",
        instance_key="demo_instance",
        model_path=model_path,
        recreate=True,
        ensure_running=True,
        start_on_create=True,
    )

    assert instance is client["instances"]["demo_instance"]
    assert [name for name, _payload in instance.calls] == ["reset", "start"]


def test_ensure_instance_does_not_require_spx_python_helpers(
    tmp_path: Path,
    monkeypatch,
) -> None:
    model_path = tmp_path / "model.yaml"
    model_path.write_text(
        "name: demo\nattributes:\n  value: 1\n",
        encoding="utf-8",
    )
    client = _FakeClient()
    original_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "spx_python.helpers" or name.startswith("spx_python.helpers."):
            raise AssertionError("spx_python.helpers should not be imported by runtime bootstrap")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    instance = bootstrap.ensure_instance(
        client,
        model_id="demo.model",
        instance_key="demo_instance",
        model_path=model_path,
        recreate=True,
        ensure_running=False,
        start_on_create=False,
    )

    assert instance is client["instances"]["demo_instance"]


def test_ensure_instance_uses_generate_for_meta_parameter_defaults(tmp_path: Path) -> None:
    model_path = tmp_path / "model.yaml"
    model_path.write_text(
        "\n".join(
            [
                "name: demo",
                "meta_parameters:",
                "  modbus_port:",
                "    type: int",
                "    default: 5027",
                "  modbus_unit_id:",
                "    type: int",
                "    default: 11",
                "attributes:",
                "  value: 1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    client = _FakeClient()

    instance = bootstrap.ensure_instance(
        client,
        model_id="demo.model",
        instance_key="demo_instance",
        model_path=model_path,
        recreate=True,
        ensure_running=False,
        start_on_create=False,
    )

    assert instance is client["instances"]["demo_instance"]
    assert client["instances"].generate_calls == [
        {
            "template": "demo.model",
            "count": 1,
            "name": "demo_instance",
            "parameters": {
                "modbus_port": {"cycle": [5027]},
                "modbus_unit_id": {"cycle": [11]},
            },
        }
    ]


def test_summarize_runtime_instance_extracts_modbus_slave_endpoint_from_attr_mapping() -> None:
    instance = _FakeInstance()

    payload = bootstrap.summarize_runtime_instance(
        instance,
        model_id="demo.model",
        instance_key="demo_instance",
    )

    assert payload["endpoint_details"] == {
        "modbus_slave": {
            "port": 5027,
            "unit_id": 11,
        }
    }


def test_summarize_runtime_instance_falls_back_to_model_payload_for_modbus_slave_endpoint() -> None:
    instance = _FakeInstance()
    instance._doc["communication"] = {}

    payload = bootstrap.summarize_runtime_instance(
        instance,
        model_id="demo.model",
        instance_key="demo_instance",
        model_payload={
            "communication": [
                {
                    "modbus_slave": {
                        "host": "127.0.0.1",
                        "port": "5027",
                        "id": "11",
                    }
                }
            ]
        },
    )

    assert payload["endpoint_details"] == {
        "modbus_slave": {
            "host": "127.0.0.1",
            "port": 5027,
            "unit_id": 11,
        }
    }
