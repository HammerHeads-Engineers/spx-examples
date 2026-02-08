# SPDX-License-Identifier: MIT

import os
import struct
import unittest

from tests.common.modbus_utils import wait_for_modbus_endpoint
from tests.common.spx_utils import require_existing_instance, wait_for_condition
from tests.devices.modbus_sut_base import ModbusTcpClient


SPX_BASE_URL = os.environ.get("SPX_BASE_URL", "http://localhost:8000")
INSTANCE_KEY = "spx_energy_meter_pac3200_modbus"
MODEL_ID = "Energy.EnergyMeterPac3200.Modbus"


def _decode_float(registers):
    if not registers or len(registers) != 2:
        raise ValueError(f"Expected 2 registers, got {registers}")
    packed = struct.pack(">HH", int(registers[0]) & 0xFFFF, int(registers[1]) & 0xFFFF
    )
    return struct.unpack(">f", packed)[0]


class TestModbusPac3200Smoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if ModbusTcpClient is None:  # pragma: no cover - dependency missing
            raise unittest.SkipTest(
                "pymodbus is not available. Install pymodbus to run Modbus integration tests."
            )

        try:
            import spx_python  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise unittest.SkipTest(f"spx_python not available: {exc}") from exc

        product_key = os.environ.get("SPX_PRODUCT_KEY")
        if not product_key:
            raise unittest.SkipTest("SPX_PRODUCT_KEY must be set to run integration tests.")

        cls._client = spx_python.init(address=SPX_BASE_URL, product_key=product_key)
        cls._instance = require_existing_instance(
            cls._client,
            INSTANCE_KEY,
            expected_model_id=MODEL_ID,
            ensure_running=False,
        )

        cls._model_changed = False
        try:
            cls._instance.stop()
        except Exception:
            pass
        try:
            cls._instance.reset()
        except Exception:
            pass
        try:
            cls._instance.start()
        except Exception:
            pass

    def setUp(self):
        instance = getattr(self.__class__, "_instance", None)
        if instance is None:  # pragma: no cover - defensive
            self.skipTest("PAC3200 instance not initialised")

        comms = instance["communication"]
        preferred_comm_key = "modbus_slave" if "modbus_slave" in comms else "modbus_tcp"
        try:
            self._modbus_port, self._modbus_unit_id = wait_for_modbus_endpoint(
                instance,
                comm_keys=(
                    preferred_comm_key,
                    "modbus_slave" if preferred_comm_key == "modbus_tcp" else "modbus_tcp",
                ),
                timeout=10.0,
                interval=0.2,
            )
        except TimeoutError as exc:
            self.skipTest(str(exc))

    def _read_float(self, client, address: int) -> float:
        try:
            result = client.read_holding_registers(address, count=2, slave=self._modbus_unit_id)
        except TypeError:
            result = client.read_holding_registers(address, count=2, unit=self._modbus_unit_id)
        if result is None:
            raise RuntimeError(f"No response at address {address}")
        if result.isError():  # pragma: no cover - delegated to pymodbus
            raise RuntimeError(f"Modbus read failed at address {address}")
        return float(_decode_float(result.registers))

    def test_pac3200_registers_are_readable(self):
        client = ModbusTcpClient(host="127.0.0.1", port=self._modbus_port)
        try:
            ready = wait_for_condition(client.connect, timeout=5.0, interval=0.2)
            if not ready:
                self.skipTest(f"Modbus server not reachable at 127.0.0.1:{self._modbus_port}")

            voltage_l1 = self._read_float(client, 1)
            current_l1 = self._read_float(client, 13)
            frequency = self._read_float(client, 55)
            power_factor = self._read_float(client, 69)
            apparent_power = self._read_float(client, 63)
            active_power = self._read_float(client, 65)

            self.assertGreater(voltage_l1, 150.0)
            self.assertLess(voltage_l1, 270.0)
            self.assertGreater(current_l1, -200.0)
            self.assertLess(current_l1, 200.0)
            self.assertGreater(frequency, 45.0)
            self.assertLess(frequency, 65.0)
            self.assertGreater(power_factor, -1.1)
            self.assertLess(power_factor, 1.1)

            expected_power = power_factor * apparent_power
            self.assertAlmostEqual(active_power, expected_power, delta=max(50.0, abs(expected_power) * 0.2))
        finally:
            client.close()
