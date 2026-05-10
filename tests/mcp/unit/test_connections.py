# SPDX-License-Identifier: MIT

import pytest

from spx_mcp.backend import connections


class DummyConnectionNode:
    def __init__(self, name: str, definition) -> None:
        self.name = name
        self.definition = definition
        self.start_calls = 0
        self.stop_calls = 0
        self.run_calls = 0

    def get(self):
        return {
            "name": self.name,
            "attr": {
                "definition": {
                    "value": self.definition,
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

    def run(self):
        self.run_calls += 1
        return {"result": True}


class DummyConnections:
    def __init__(self, payloads=None) -> None:
        self.nodes = {
            name: DummyConnectionNode(name, payload)
            for name, payload in dict(payloads or {}).items()
        }
        self.start_calls = 0
        self.stop_calls = 0

    def __getitem__(self, key):
        return self.nodes[key]

    def __setitem__(self, key, value) -> None:
        self.nodes[key] = DummyConnectionNode(key, value)

    def __delitem__(self, key) -> None:
        del self.nodes[key]

    def keys(self):
        return self.nodes.keys()

    def start(self):
        self.start_calls += 1
        return {"result": True}

    def stop(self):
        self.stop_calls += 1
        return {"result": True}


class DummyClient(dict):
    def __init__(self, payloads=None) -> None:
        super().__init__()
        self["connections"] = DummyConnections(payloads)


def test_build_connection_definition_from_endpoint_parts() -> None:
    payload = connections.build_connection_definition(
        source_instance_key="Weather_Gateway",
        source_attr_path="attributes/k__brightness_lux/external_value",
        target_instance_key="PV_Physics",
        target_attr_path="k__illuminance_lux",
    )

    assert payload == {
        "from": "$out(Weather_Gateway.k__brightness_lux)",
        "to": "$in(PV_Physics.k__illuminance_lux)",
    }


def test_build_connection_definition_preserves_explicit_expressions() -> None:
    payload = connections.build_connection_definition(
        from_expr="$out(A.value)",
        to_expr="$in(B.value)",
    )

    assert payload == {
        "from": "$out(A.value)",
        "to": "$in(B.value)",
    }


def test_normalize_attr_endpoint_rejects_nested_paths() -> None:
    with pytest.raises(ValueError, match="single attribute"):
        connections.normalize_attr_endpoint(
            "attributes/group/nested/external_value",
            "source_attr_path",
        )


def test_upsert_connection_creates_and_starts_runtime_connection() -> None:
    client = DummyClient()

    payload = connections.upsert_connection(
        client,
        "Vaisala_to_PV",
        source_instance_key="Weather_Gateway",
        source_attr_path="k__brightness_lux",
        target_instance_key="PV_Physics",
        target_attr_path="k__illuminance_lux",
        start=True,
    )

    assert payload["connection_name"] == "Vaisala_to_PV"
    assert payload["replaced"] is False
    assert payload["started"] is True
    assert client["connections"]["Vaisala_to_PV"].start_calls == 1
    assert connections.list_connections(client) == ["Vaisala_to_PV"]


def test_upsert_connection_replaces_existing_after_stop() -> None:
    client = DummyClient(
        {
            "demo": {
                "from": "$out(Old.value)",
                "to": "$in(Target.value)",
            }
        }
    )

    payload = connections.upsert_connection(
        client,
        "demo",
        from_expr="$out(New.value)",
        to_expr="$in(Target.value)",
    )

    assert payload["replaced"] is True
    assert payload["stopped_existing"] is True
    assert client["connections"]["demo"].definition["from"] == "$out(New.value)"


def test_upsert_connection_rejects_duplicate_without_replace() -> None:
    client = DummyClient(
        {
            "demo": {
                "from": "$out(Old.value)",
                "to": "$in(Target.value)",
            }
        }
    )

    with pytest.raises(ValueError, match="already exists"):
        connections.upsert_connection(
            client,
            "demo",
            from_expr="$out(New.value)",
            to_expr="$in(Target.value)",
            replace=False,
        )


def test_delete_connection_stops_and_removes_connection() -> None:
    client = DummyClient(
        {
            "demo": {
                "from": "$out(Source.value)",
                "to": "$in(Target.value)",
            }
        }
    )

    payload = connections.delete_connection(client, "demo")

    assert payload["deleted"] is True
    assert connections.list_connections(client) == []


def test_start_stop_and_run_connection_delegate_to_runtime_node() -> None:
    client = DummyClient(
        {
            "demo": {
                "from": "$out(Source.value)",
                "to": "$in(Target.value)",
            }
        }
    )

    assert connections.start_connections(client)["result"] == {"result": True}
    assert connections.stop_connections(client)["result"] == {"result": True}
    assert connections.start_connection(client, "demo")["result"] == {"result": True}
    assert connections.stop_connection(client, "demo")["result"] == {"result": True}
    assert connections.run_connection(client, "demo")["result"] == {"result": True}

    node = client["connections"]["demo"]
    assert node.start_calls == 1
    assert node.stop_calls == 1
    assert node.run_calls == 1
