# SPDX-License-Identifier: MIT

import pytest

from spx_mcp.backend import instances


class DummyReadableNode:
    def __init__(self, children=None, internal_value=None, external_value=None) -> None:
        self.children = dict(children or {})
        self.internal_value = internal_value
        self.external_value = external_value

    def __getitem__(self, key):
        return self.children[key]


class DummyWritableInstance:
    def __init__(self) -> None:
        self.calls = []

    def put_attr(self, path: str, value) -> None:
        self.calls.append((path, value))


class DummyScenarioNode:
    def __init__(self, name: str, payload) -> None:
        self.name = name
        self.payload = payload
        self.start_calls = 0
        self.stop_calls = 0

    def get(self):
        return {
            "name": self.name,
            "attr": {
                "definition": {
                    "value": self.payload,
                }
            },
            "children": [],
        }

    def start(self):
        self.start_calls += 1
        return {"result": True}

    def stop(self):
        self.stop_calls += 1
        return {"result": True}


class DummyScenarioContainer:
    def __init__(self, payloads=None) -> None:
        self.nodes = {
            name: DummyScenarioNode(name, payload)
            for name, payload in dict(payloads or {}).items()
        }

    def __contains__(self, key):
        return key in self.nodes

    def __getitem__(self, key):
        return self.nodes[key]

    def __setitem__(self, key, value) -> None:
        self.nodes[key] = DummyScenarioNode(key, value)

    def __delitem__(self, key) -> None:
        del self.nodes[key]

    def keys(self):
        return self.nodes.keys()


class DummyScenarioInstance:
    def __init__(self, payloads=None) -> None:
        self.children = {
            "scenarios": DummyScenarioContainer(payloads),
        }

    def __getitem__(self, key):
        return self.children[key]


def test_get_attribute_values_batches_multiple_paths(monkeypatch) -> None:
    monkeypatch.setattr(
        instances,
        "get_attribute_value",
        lambda instance, attr_path: f"value:{attr_path}",
    )

    payload = instances.get_attribute_values(object(), ["a", "b"])

    assert payload == {
        "a": "value:a",
        "b": "value:b",
    }


def test_get_attribute_value_defaults_to_external_value() -> None:
    instance = DummyReadableNode(
        {
            "attributes": DummyReadableNode(
                {
                    "demo": DummyReadableNode(
                        internal_value=12.5,
                        external_value=41.5,
                    )
                }
            )
        }
    )

    payload = instances.get_attribute_value(instance, "attributes/demo")

    assert payload == 41.5


def test_get_attribute_value_preserves_explicit_internal_value_path() -> None:
    instance = DummyReadableNode(
        {
            "attributes": DummyReadableNode(
                {
                    "demo": DummyReadableNode(
                        internal_value=12.5,
                        external_value=41.5,
                    )
                }
            )
        }
    )

    payload = instances.get_attribute_value(instance, "attributes/demo/internal_value")

    assert payload == 12.5


def test_list_instance_scenarios_returns_registered_names() -> None:
    instance = DummyScenarioInstance(
        {
            "alpha": {"duration": 1.0},
            "beta": {"duration": 2.0},
        }
    )

    payload = instances.list_instance_scenarios(instance)

    assert payload == ["alpha", "beta"]


def test_get_scenario_doc_returns_runtime_scenario_document() -> None:
    instance = DummyScenarioInstance(
        {
            "alpha": {"duration": 1.0},
        }
    )

    payload = instances.get_scenario_doc(instance, "alpha")

    assert payload["name"] == "alpha"
    assert payload["attr"]["definition"]["value"] == {"duration": 1.0}


def test_resolve_attribute_read_path_defaults_to_external_value() -> None:
    assert (
        instances.resolve_attribute_read_path("attributes/demo")
        == "attributes/demo/external_value"
    )


def test_resolve_attribute_write_path_defaults_to_internal_value() -> None:
    assert (
        instances.resolve_attribute_write_path("attributes/demo")
        == "attributes/demo/internal_value"
    )


def test_set_attribute_value_defaults_to_internal_value() -> None:
    instance = DummyWritableInstance()

    resolved_path = instances.set_attribute_value(instance, "attributes/demo", 12.5)

    assert resolved_path == "attributes/demo/internal_value"
    assert instance.calls == [("attributes/demo/internal_value", 12.5)]


def test_set_attribute_value_preserves_explicit_external_value_path() -> None:
    instance = DummyWritableInstance()

    resolved_path = instances.set_attribute_value(
        instance,
        "attributes/demo/external_value",
        12.5,
    )

    assert resolved_path == "attributes/demo/external_value"
    assert instance.calls == [("attributes/demo/external_value", 12.5)]


def test_set_attribute_value_preserves_explicit_internal_value_path() -> None:
    instance = DummyWritableInstance()

    resolved_path = instances.set_attribute_value(
        instance,
        "attributes/demo/internal_value",
        12.5,
    )

    assert resolved_path == "attributes/demo/internal_value"
    assert instance.calls == [("attributes/demo/internal_value", 12.5)]


def test_set_attribute_values_returns_resolved_paths(monkeypatch) -> None:
    monkeypatch.setattr(
        instances,
        "set_attribute_value",
        lambda instance, attr_path, value: f"{attr_path}/resolved",
    )

    payload = instances.set_attribute_values(
        object(),
        {
            "one": 1,
            "two": 2,
        },
    )

    assert payload == {
        "one": "one/resolved",
        "two": "two/resolved",
    }


def test_upsert_instance_scenario_creates_new_runtime_scenario() -> None:
    instance = DummyScenarioInstance()

    payload = instances.upsert_instance_scenario(
        instance,
        "alpha",
        {"duration": 5.0},
    )

    assert payload["scenario_name"] == "alpha"
    assert payload["replaced"] is False
    assert payload["started"] is False
    assert payload["start_result"] is None
    assert payload["scenario"]["attr"]["definition"]["value"] == {"duration": 5.0}


def test_upsert_instance_scenario_rejects_duplicate_without_replace() -> None:
    instance = DummyScenarioInstance(
        {
            "alpha": {"duration": 1.0},
        }
    )

    with pytest.raises(ValueError, match="already exists"):
        instances.upsert_instance_scenario(
            instance,
            "alpha",
            {"duration": 5.0},
            replace=False,
        )


def test_upsert_instance_scenario_stops_existing_and_can_autostart() -> None:
    instance = DummyScenarioInstance(
        {
            "alpha": {"duration": 1.0},
        }
    )
    original = instance["scenarios"]["alpha"]

    payload = instances.upsert_instance_scenario(
        instance,
        "alpha",
        {"duration": 5.0},
        start=True,
    )

    replacement = instance["scenarios"]["alpha"]
    assert payload["replaced"] is True
    assert payload["started"] is True
    assert payload["start_result"] == {"result": True}
    assert original.stop_calls == 1
    assert replacement.start_calls == 1


def test_upsert_instance_scenario_rejects_non_mapping_payload() -> None:
    instance = DummyScenarioInstance()

    with pytest.raises(ValueError, match="scenario must be a mapping"):
        instances.upsert_instance_scenario(instance, "alpha", ["not", "a", "dict"])


def test_start_instance_scenario_invokes_runtime_start() -> None:
    instance = DummyScenarioInstance(
        {
            "alpha": {"duration": 1.0},
        }
    )

    payload = instances.start_instance_scenario(instance, "alpha")

    assert payload["scenario_name"] == "alpha"
    assert payload["result"] == {"result": True}
    assert instance["scenarios"]["alpha"].start_calls == 1


def test_stop_instance_scenario_invokes_runtime_stop() -> None:
    instance = DummyScenarioInstance(
        {
            "alpha": {"duration": 1.0},
        }
    )

    payload = instances.stop_instance_scenario(instance, "alpha")

    assert payload["scenario_name"] == "alpha"
    assert payload["result"] == {"result": True}
    assert instance["scenarios"]["alpha"].stop_calls == 1


def test_delete_instance_scenario_stops_then_deletes_by_default() -> None:
    instance = DummyScenarioInstance(
        {
            "alpha": {"duration": 1.0},
        }
    )
    scenario = instance["scenarios"]["alpha"]

    payload = instances.delete_instance_scenario(instance, "alpha")

    assert payload == {
        "scenario_name": "alpha",
        "deleted": True,
        "stopped": True,
        "stop_result": {"result": True},
    }
    assert scenario.stop_calls == 1
    assert "alpha" not in instance["scenarios"]


def test_delete_instance_scenario_can_skip_stop() -> None:
    instance = DummyScenarioInstance(
        {
            "alpha": {"duration": 1.0},
        }
    )
    scenario = instance["scenarios"]["alpha"]

    payload = instances.delete_instance_scenario(
        instance,
        "alpha",
        stop_if_running=False,
    )

    assert payload == {
        "scenario_name": "alpha",
        "deleted": True,
        "stopped": False,
        "stop_result": None,
    }
    assert scenario.stop_calls == 0
    assert "alpha" not in instance["scenarios"]


def test_ramp_attribute_value_applies_even_steps(monkeypatch) -> None:
    writes = []
    clock = {"value": 100.0}

    def fake_sleep(seconds: float) -> None:
        clock["value"] += seconds

    def fake_monotonic() -> float:
        return clock["value"]

    monkeypatch.setattr(instances, "get_attribute_value", lambda instance, attr_path: 10.0)
    monkeypatch.setattr(
        instances,
        "set_attribute_value",
        lambda instance, attr_path, value: writes.append((attr_path, value)) or "attributes/demo/internal_value",
    )

    payload = instances.ramp_attribute_value(
        object(),
        "attributes/demo",
        20.0,
        duration_s=4.0,
        steps=4,
        sleep_fn=fake_sleep,
        monotonic_fn=fake_monotonic,
    )

    assert [value for _, value in writes] == [12.5, 15.0, 17.5, 20.0]
    assert payload["start_value"] == 10.0
    assert payload["target_value"] == 20.0
    assert payload["interval_s"] == 1.0
    assert payload["final_value"] == 10.0
    assert payload["resolved_path"] == "attributes/demo/internal_value"
    assert payload["applied"][-1]["elapsed_s"] == 4.0


def test_ramp_attribute_value_respects_explicit_start_value(monkeypatch) -> None:
    writes = []
    reads = {"count": 0}

    def fake_get_attribute_value(instance, attr_path):
        reads["count"] += 1
        return 30.0

    monkeypatch.setattr(
        instances,
        "get_attribute_value",
        fake_get_attribute_value,
    )
    monkeypatch.setattr(
        instances,
        "set_attribute_value",
        lambda instance, attr_path, value: writes.append(value) or "attributes/demo/internal_value",
    )

    payload = instances.ramp_attribute_value(
        object(),
        "attributes/demo",
        30.0,
        duration_s=0.0,
        steps=3,
        start_value=0.0,
        sleep_fn=lambda seconds: None,
        monotonic_fn=lambda: 0.0,
    )

    assert writes == [10.0, 20.0, 30.0]
    assert payload["start_value"] == 0.0
    assert payload["final_value"] == 30.0
    assert reads["count"] == 1


def test_ramp_attribute_value_rejects_invalid_inputs() -> None:
    with pytest.raises(ValueError):
        instances.ramp_attribute_value(
            object(),
            "attributes/demo",
            20.0,
            duration_s=1.0,
            steps=0,
        )

    with pytest.raises(ValueError):
        instances.ramp_attribute_value(
            object(),
            "attributes/demo",
            "high",
            duration_s=1.0,
            steps=1,
            start_value=0.0,
        )
