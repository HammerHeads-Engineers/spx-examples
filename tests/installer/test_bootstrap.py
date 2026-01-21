# SPDX-License-Identifier: MIT
"""Tests for the installer bootstrap helper."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from installer import bootstrap


@pytest.fixture()
def model_bundle(tmp_path: Path) -> Path:
    model_path = tmp_path / "model.yaml"
    model_path.write_text("name: dummy_model\n", encoding="utf-8")
    bundle = {
        "license_key": "XYZ",
        "models": [
            {"id": "dummy", "path": str(model_path)},
        ],
        "instances": [
            {"model_id": "dummy", "instance_key": "inst_1"},
        ],
        "start_instances": ["inst_1"],
    }
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    return bundle_path


def test_bootstrap_uses_http_when_sdk_missing(monkeypatch: pytest.MonkeyPatch, model_bundle: Path) -> None:
    calls: list[tuple[str, str]] = []

    class DummyResponse:
        def raise_for_status(self) -> None:
            return None

    class DummySession:
        def __init__(self) -> None:
            self.headers = {}

        def post(self, url, headers=None, params=None, data=None, timeout=None):
            calls.append((url, data))
            return DummyResponse()

    monkeypatch.setattr(bootstrap, "spx_python", None)
    monkeypatch.setattr(bootstrap, "requests", SimpleNamespace(Session=lambda: DummySession()))
    monkeypatch.setattr(bootstrap, "wait_for_server", lambda api_url: None)

    bootstrap.bootstrap(model_bundle, "http://example")

    assert calls
    assert calls[0][0] == "http://example/models"
    assert "dummy_model" in calls[0][1]


def test_bootstrap_uses_sdk_when_available(monkeypatch: pytest.MonkeyPatch, model_bundle: Path) -> None:
    class FakeInstance:
        def __init__(self) -> None:
            self.started = False

        def start(self) -> None:
            self.started = True

    class FakeInstances:
        def __init__(self) -> None:
            self._store = {}

        def __getitem__(self, key: str) -> FakeInstance:
            return self._store[key]

        def __setitem__(self, key: str, model_id: str) -> None:  # noqa: ARG002
            self._store[key] = FakeInstance()

    class FakeClient(dict):
        def __init__(self) -> None:
            super().__init__()
            self["models"] = {}
            self["instances"] = FakeInstances()

    fake_client = FakeClient()

    class FakeSPX(SimpleNamespace):
        @staticmethod
        def init(address, product_key):
            assert address == "http://example"
            assert product_key == "XYZ"
            return fake_client

    monkeypatch.setattr(bootstrap, "spx_python", FakeSPX)
    monkeypatch.setattr(bootstrap, "wait_for_server", lambda api_url: None)

    bootstrap.bootstrap(model_bundle, "http://example")
    assert "dummy" in fake_client["models"]
    assert "inst_1" in fake_client["instances"]._store
    assert fake_client["instances"]["inst_1"].started is True


def test_bootstrap_skip_instances(monkeypatch: pytest.MonkeyPatch, model_bundle: Path) -> None:
    class FakeInstances:
        def __init__(self) -> None:
            self._store = {}

        def __setitem__(self, key: str, model_id: str) -> None:  # noqa: ARG002
            self._store[key] = object()

    class FakeClient(dict):
        def __init__(self) -> None:
            super().__init__()
            self["models"] = {}
            self["instances"] = FakeInstances()

    fake_client = FakeClient()

    class FakeSPX(SimpleNamespace):
        @staticmethod
        def init(address, product_key):
            assert address == "http://example"
            assert product_key == "XYZ"
            return fake_client

    monkeypatch.setattr(bootstrap, "spx_python", FakeSPX)
    monkeypatch.setattr(bootstrap, "wait_for_server", lambda api_url: None)

    bootstrap.bootstrap(model_bundle, "http://example", skip_instances=True)
    assert "dummy" in fake_client["models"]
    assert fake_client["instances"]._store == {}
