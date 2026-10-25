"""Qualify the shipped CSMS/EVSE pair over an actual WebSocket connection."""

import os
from pathlib import Path
import socket
import time

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
pytestmark = pytest.mark.skipif(os.getenv("SPX_MODEL_RUNTIME_TESTS") != "1", reason="requires SPX runtime fixture")


def test_shipped_pair_accepts_boot_and_reports_energy_and_power():
    from spx_core.system import Model
    from spx_core.system.param_resolver import resolve_definition_with_params
    from spx_core.communications.ocpp import OcppProtocol
    from spx_sdk.registry import register_class
    register_class(name="ocpp")(OcppProtocol)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    models = []
    try:
        for device, parameters in (
            ("csms", {"ocpp_server_host": "127.0.0.1", "ocpp_server_port": port}),
            ("evse", {"ocpp_endpoint": f"ws://127.0.0.1:{port}/ocpp"}),
        ):
            source = ROOT / f"library/domains/energy/{device}/generic/{device}__ocpp.yaml"
            definition = yaml.safe_load(source.read_text(encoding="utf-8"))
            assert not any(scenario.get("enabled", False) for scenario in definition["scenarios"].values()), "Demo fault scenarios must require an explicit Start"
            definition, _ = resolve_definition_with_params(
                definition, specs=definition["meta_parameters"], provided=parameters,
                allow_defaults=True, require_declared=True,
            )
            # Faster test cadence preserves the shipped binding and payload.
            if device == "evse":
                definition["communication"][0]["ocpp"]["bindings"]["meter_values"]["interval"] = 0.2
            model = Model(name=f"qa_{device}", definition=definition)
            models.append(model)
            model.reset()
            model.prepare()
            model.start()
        csms, evse = models
        attrs = evse["attributes"]
        attrs["session_active"].internal_value = 1
        attrs["commanded_current_a"].internal_value = 16.0
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            csms.run()
            evse.run()
            if attrs["boot_status"].internal_value == "Accepted" and csms["attributes"]["last_power_w"].internal_value > 0:
                break
            time.sleep(0.02)
        assert attrs["boot_status"].internal_value == "Accepted"
        assert csms["attributes"]["last_power_w"].internal_value == pytest.approx(attrs["power_kw"].internal_value * 1000, abs=1)
        assert csms["attributes"]["last_energy_wh"].internal_value == pytest.approx(attrs["energy_wh"].internal_value, abs=1)
        assert all(model.state.name != "FAULT" for model in models)
    finally:
        for model in reversed(models):
            model.destroy()
