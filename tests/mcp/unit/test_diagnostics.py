# SPDX-License-Identifier: MIT

from spx_mcp.backend import diagnostics


def test_diagnose_instance_tolerates_missing_communication(monkeypatch) -> None:
    monkeypatch.setattr(
        diagnostics,
        "get_instance_doc",
        lambda client, instance_key: {
            "state": "idle",
            "model_id": "example_model",
        },
    )
    monkeypatch.setattr(
        diagnostics,
        "collect_logs",
        lambda client, instance_key, attr_path=None: {
            "instance_key": instance_key,
            "entries": [],
        },
    )

    def raise_missing(client, instance_key, protocol=None):
        raise KeyError("communication")

    monkeypatch.setattr(diagnostics, "get_communication", raise_missing)

    result = diagnostics.diagnose_instance(object(), "demo_instance")

    assert result["state"] == "idle"
    assert result["model_id"] == "example_model"
    assert result["communication"]["payload"] is None
    assert "communication" in result["communication"]["error"]


def test_diagnose_instance_reports_binding_errors(monkeypatch) -> None:
    monkeypatch.setattr(
        diagnostics,
        "get_instance_doc",
        lambda client, instance_key: {
            "state": "running",
            "model_id": "example_model",
        },
    )
    monkeypatch.setattr(
        diagnostics,
        "collect_logs",
        lambda client, instance_key, attr_path=None: {
            "instance_key": instance_key,
            "entries": [],
        },
    )
    monkeypatch.setattr(
        diagnostics,
        "get_communication",
        lambda client, instance_key, protocol=None: {
            "instance_key": instance_key,
            "protocol": protocol,
            "path": "communication/modbus",
            "payload": {},
        },
    )

    def raise_missing(client, instance_key, protocol):
        raise KeyError("bindings")

    monkeypatch.setattr(diagnostics, "get_bindings", raise_missing)

    result = diagnostics.diagnose_instance(
        object(),
        "demo_instance",
        protocol="modbus",
    )

    assert result["bindings"]["payload"] is None
    assert "bindings" in result["bindings"]["error"]
