"""Exercise the shipped LwM2M model through the Leshan registered endpoint."""

import os
from pathlib import Path
import uuid

import pytest
import requests
import yaml

pytestmark = pytest.mark.skipif(os.getenv("SPX_MODEL_RUNTIME_TESTS") != "1", reason="requires SPX runtime fixture")


def test_model_registration_diagnostics_write_and_reconnect():
    from spx_core.system import Model
    from spx_core.communications.lwm2m.client import Lwm2mClient
    from spx_sdk.registry import register_class
    register_class(name="lwm2m")(Lwm2mClient)
    from spx_core.system.param_resolver import resolve_definition_with_params
    source = Path(__file__).resolve().parents[3] / "library/domains/environment/sensor/generic/environment_sensor__lwm2m.yaml"
    definition = yaml.safe_load(source.read_text())
    endpoint = f"spx-qa-model-{uuid.uuid4().hex[:8]}"
    host = os.environ.get("LWM2M_TEST_HOST", "127.0.0.1")
    definition, _ = resolve_definition_with_params(definition, specs=definition["meta_parameters"],
        provided={"lwm2m_endpoint": endpoint, "lwm2m_server_host": host}, allow_defaults=True, require_declared=True)
    model = Model(name="sensor_regression", definition=definition)
    client = model["communication"]["lwm2m"]
    rest = os.environ.get("LWM2M_TEST_REST", f"http://{host}:8080")
    base = f"{rest}/api/clients/{endpoint}"
    try:
        model.prepare()
        client.start()
        model.run()
        assert model["attributes"]["lwm2m_connected"].internal_value == 1
        read = requests.get(f"{base}/3303/0/5700", params={"format": "TEXT", "timeout": 3}, timeout=6)
        assert read.json()["success"], read.text
        assert float(read.json()["content"]["value"]) == pytest.approx(model["attributes"]["k__temperature_c"].internal_value)
        write = requests.put(f"{base}/3308/0/5900", params={"format": "TEXT", "timeout": 3},
            json={"id": 5900, "kind": "singleResource", "type": "float", "value": 24.5}, timeout=6)
        assert write.json()["success"], write.text
        assert model["attributes"]["k__target_c"].internal_value == 24.5
        model.run()
        assert model["attributes"]["lwm2m_request_counter"].internal_value >= 2
        scenario = model["scenarios"]["lwm2m_reconnect"]
        scenario.start()
        model.run()
        assert not client.registered
        scenario.stop()
        assert client.registered
    finally:
        model.destroy()
