"""Qualify the CSMS registration and two charging transactions on the wire."""

import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
pytestmark = pytest.mark.skipif(
    os.getenv("SPX_MODEL_RUNTIME_TESTS") != "1", reason="requires SPX runtime fixture"
)


def test_csms_supports_two_transactions_and_current_utc_time():
    from spx_core.system import Model
    from spx_core.system.param_resolver import resolve_definition_with_params
    from spx_core.communications.ocpp import OcppProtocol
    from spx_sdk.registry import register_class
    from websockets.asyncio.client import connect

    register_class(name="ocpp")(OcppProtocol)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    source = ROOT / "library/domains/energy/csms/generic/csms__ocpp.yaml"
    definition = yaml.safe_load(source.read_text())
    definition, _ = resolve_definition_with_params(
        definition,
        specs=definition["meta_parameters"],
        provided={"ocpp_server_host": "127.0.0.1", "ocpp_server_port": port},
    )
    model = Model(name="csms_transaction_regression", definition=definition)
    model.reset()
    model.prepare()
    model.start()

    async def exercise():
        async with connect(
            f"ws://127.0.0.1:{port}/ocpp", subprotocols=["ocpp1.6"]
        ) as ws:

            async def call(action, payload):
                await ws.send(json.dumps([2, action, action, payload]))
                response = json.loads(await asyncio.wait_for(ws.recv(), 3))
                assert response[:2] == [3, action], response
                return response[2]

            before = datetime.now(timezone.utc)
            boot = await call(
                "BootNotification",
                {"chargePointVendor": "QA", "chargePointModel": "RC107"},
            )
            assert boot["status"] == "Accepted"
            clock = datetime.fromisoformat(boot["currentTime"].replace("Z", "+00:00"))
            assert before <= clock <= datetime.now(timezone.utc)
            heartbeat = await call("Heartbeat", {})
            assert heartbeat["currentTime"] >= boot["currentTime"]
            authorization = await call("Authorize", {"idTag": "QA-1"})
            assert authorization["idTagInfo"]["status"] == "Accepted"
            ids = []
            for index in range(2):
                timestamp = (
                    datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                )
                start = await call(
                    "StartTransaction",
                    {
                        "connectorId": 1,
                        "idTag": "QA-1",
                        "meterStart": index * 100,
                        "timestamp": timestamp,
                    },
                )
                ids.append(start["transactionId"])
                assert start["idTagInfo"]["status"] == "Accepted"
                await call(
                    "StopTransaction",
                    {
                        "transactionId": ids[-1],
                        "meterStop": (index + 1) * 100,
                        "timestamp": timestamp,
                    },
                )
            assert ids == [1, 2]
            attrs = model["attributes"]
            assert attrs["last_transaction_id"].internal_value == 2
            assert attrs["last_meter_stop_wh"].internal_value == 200
            attrs["k__authorization_status"].internal_value = "Invalid"
            assert (await call("Authorize", {"idTag": "QA-denied"}))["idTagInfo"][
                "status"
            ] == "Invalid"

    try:
        asyncio.run(exercise())
    finally:
        model.destroy()
