"""Exercise the runtime qualifier's actual client interactions without credentials."""

import json

import pytest

from tools.model_catalog import CatalogError, export_catalog
from tools.qualify_catalog import qualify_catalog
from tests.catalog.test_distribution import baseline, source


class Instance:
    def __init__(self, fail=False):
        self.state = "INITIALIZED"
        self.fail = fail

    def reset(self):
        self.state = "INITIALIZED"

    def start(self):
        self.state = "RUNNING"

    def run(self):
        if self.fail:
            raise RuntimeError("test-private-token must not appear in public reports")

    def stop(self):
        self.state = "STOPPED"

    def get(self):
        return {"state": self.state, "attr": {"temperature_c": {"value": 20.0}}}


class Instances(dict):
    def __init__(self, fail=False):
        super().__init__()
        self.fail = fail

    def __setitem__(self, name, model):
        super().__setitem__(name, Instance(self.fail))

    def generate(self, *, template, count, name, parameters):
        assert count == 1
        self[name] = template


@pytest.mark.parametrize("fail", [False, True])
@pytest.mark.parametrize("probe", [False, True])
@pytest.mark.parametrize("exclude", [False, True])
def test_qualifier_records_runtime_stages_and_always_cleans_up(
    source, tmp_path, monkeypatch, fail, probe, exclude
):
    directory = tmp_path / "artifact"
    document = export_catalog(source, directory, "test.runtime")
    client = {"models": {}, "instances": Instances(fail)}
    monkeypatch.setenv("SPX_PRODUCT_KEY", "test-private-token")
    monkeypatch.setattr("spx_python.init", lambda **kwargs: client)

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"server_version": "v0.2.0" if probe else "v1.0.0-rc.78"}

    monkeypatch.setattr("requests.get", lambda *args, **kwargs: Response())
    report = qualify_catalog(
        directory,
        "http://localhost:18000",
        allow_writes=True,
        probe_all=probe,
        excluded_protocols=["mqtt"] if exclude else [],
    )
    assert report["server_version"] == ("0.2.0" if probe else "1.0.0-rc.78")
    assert report["status"] == ("FAILED" if fail else "PASSED")
    assert len(report["results"]) == len(document["models"]) - int(exclude)
    assert report["excluded_models"] == (["Env.EnvSensor.Mqtt"] if exclude else [])
    assert report["scope"] == (
        "compatibility-probe"
        if probe
        else ("diagnostic-subset" if exclude else "full-catalog")
    )
    assert all(row["declared_compatible"] == (not probe) for row in report["results"])
    assert all(row["registration"] == "PASSED" for row in report["results"])
    assert all(row["cleanup"] == "PASSED" for row in report["results"])
    assert not client["models"] and not client["instances"]
    assert "test-private-token" not in json.dumps(report)


def test_qualifier_rejects_nonempty_server_without_modifying_it(
    source, tmp_path, monkeypatch
):
    directory = tmp_path / "artifact"
    export_catalog(source, directory, "test.runtime")
    client = {"models": {"users_model": {}}, "instances": Instances()}
    monkeypatch.setenv("SPX_PRODUCT_KEY", "test-private-token")
    monkeypatch.setattr("spx_python.init", lambda **kwargs: client)
    monkeypatch.setattr(
        "requests.get",
        lambda *args, **kwargs: type(
            "Response",
            (),
            {
                "raise_for_status": lambda self: None,
                "json": lambda self: {"server_version": "1.0.0-rc.78"},
            },
        )(),
    )
    with pytest.raises(CatalogError, match="empty"):
        qualify_catalog(directory, "http://localhost:18000", allow_writes=True)
    assert client["models"] == {"users_model": {}}


def test_runtime_writes_require_explicit_dedicated_server_consent(tmp_path):
    with pytest.raises(CatalogError, match="allow-runtime-writes"):
        qualify_catalog(tmp_path, "http://localhost:18000")
