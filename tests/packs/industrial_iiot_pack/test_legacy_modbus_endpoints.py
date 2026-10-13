"""Legacy register maps support per-instance endpoints without changing defaults."""

import os
from pathlib import Path
import socket
import struct
import time

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
MODELS = [
    path
    for path in (ROOT / "library/domains").rglob("*.yaml")
    if "  - modbus_tcp:" in path.read_text()
]


@pytest.mark.parametrize("path", MODELS, ids=lambda path: path.stem)
def test_legacy_modbus_endpoints_keep_gateway_default_and_allow_overrides(path):
    definition = yaml.safe_load(path.read_text())
    protocol = definition["communication"][0]["modbus_tcp"]
    assert protocol["host"] == "$param(modbus_host)"
    assert protocol["port"] == "$param(modbus_port)"
    assert definition["meta_parameters"]["modbus_port"]["default"] == 502
    assert definition["meta_parameters"]["modbus_host"]["default"] == "0.0.0.0"


@pytest.mark.skipif(
    os.getenv("SPX_MODEL_RUNTIME_TESTS") != "1", reason="requires SPX runtime fixture"
)
def test_thermal_controller_read_write_on_configured_instance_port():
    from spx_core.system import Model
    from spx_core.system.param_resolver import resolve_definition_with_params
    from spx_core.communications.modbus.modbus_tcp import ModbusTCP
    from spx_sdk.registry import register_class
    from pymodbus.client import ModbusTcpClient

    register_class(name="modbus_tcp")(ModbusTCP)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    definition = yaml.safe_load(
        (
            ROOT
            / "library/domains/industrial/controller/generic/thermal_controller__modbus.yaml"
        ).read_text()
    )
    definition, _ = resolve_definition_with_params(
        definition,
        specs=definition["meta_parameters"],
        provided={"modbus_host": "127.0.0.1", "modbus_port": port},
    )
    instance = Model(name="thermal_port_regression", definition=definition)
    client = ModbusTcpClient("127.0.0.1", port=port, timeout=2)
    try:
        instance.reset()
        instance.prepare()
        instance.start()
        assert client.connect()
        unit = instance["communication"]["modbus_tcp"].id
        words = struct.unpack(">HH", struct.pack(">f", 37.5))
        assert not client.write_registers(2, list(words), device_id=unit).isError()
        deadline = time.monotonic() + 3
        while (
            instance["attributes"]["setpoint"].internal_value != 37.5
            and time.monotonic() < deadline
        ):
            time.sleep(0.02)
        assert instance["attributes"]["setpoint"].internal_value == 37.5
        result = client.read_holding_registers(2, count=2, device_id=unit)
        assert not result.isError()
        assert struct.unpack(">f", struct.pack(">HH", *result.registers))[0] == 37.5
    finally:
        client.close()
        instance.destroy()
