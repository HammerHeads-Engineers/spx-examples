# SPDX-License-Identifier: MIT

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

    def fake_ensure_instance(client, **kwargs):
        class DummyInstance:
            state = "RUNNING"

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
        },
    }
