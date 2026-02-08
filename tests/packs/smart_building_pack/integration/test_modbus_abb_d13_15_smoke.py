# SPDX-License-Identifier: MIT

import os
import time
import unittest

from tests.common.modbus_utils import wait_for_modbus_endpoint
from tests.common.spx_utils import require_existing_instance
from tests.devices.modbus_sut_base import ModbusTcpClient

SPX_BASE_URL = os.environ.get("SPX_BASE_URL", "http://localhost:8000")
INSTANCE_KEY = "spx_energy_meter_abb_d13_15_modbus"
MODEL_ID = "Energy.EnergyMeterAbbD13_15.Modbus"


def _decode_u32(registers):
    if len(registers) != 2:
        raise ValueError(f"Expected 2 registers, got {len(registers)}")
    return (int(registers[0]) << 16) | int(registers[1])


def _decode_i32(registers):
    value = _decode_u32(registers)
    if value & 0x80000000:
        value -= 0x100000000
    return value


def _read_attr(instance, name):
    try:
        attr = instance["attributes"][name]
    except Exception:
        try:
            attr = instance[name]
        except Exception:
            return None
    value = getattr(attr, "internal_value", attr)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class TestModbusAbbD13_15Smoke(unittest.TestCase):
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

        time.sleep(0.2)

        try:
            cls._modbus_port, cls._modbus_unit_id = wait_for_modbus_endpoint(
                cls._instance,
                comm_keys=("modbus_slave", "modbus_tcp"),
                timeout=10.0,
                interval=0.2,
            )
        except TimeoutError as exc:
            raise unittest.SkipTest(str(exc)) from exc

    def _read_holding(self, address, count):
        client = ModbusTcpClient(host="127.0.0.1", port=self._modbus_port, timeout=2.0)
        try:
            if not client.connect():
                self.skipTest(f"Modbus server not reachable at 127.0.0.1:{self._modbus_port}")
            try:
                result = client.read_holding_registers(address, count=count, slave=self._modbus_unit_id)
            except TypeError:
                result = client.read_holding_registers(address, count=count, unit=self._modbus_unit_id)
            if result is None or result.isError():  # pragma: no cover - delegated to pymodbus
                raise RuntimeError(f"Modbus read failed at address {address}")
            return result.registers
        finally:
            client.close()

    def test_voltage_current_and_power_registers(self):
        # Voltage L1-N @ 0x5B00 (0.1 V units)
        regs = self._read_holding(23296, 2)
        voltage_l1_n = _decode_u32(regs) * 0.1
        self.assertGreater(voltage_l1_n, 200.0)
        self.assertLess(voltage_l1_n, 260.0)

        # Current L1 @ 0x5B0C (0.01 A units)
        regs = self._read_holding(23308, 2)
        current_l1 = _decode_u32(regs) * 0.01
        self.assertGreater(abs(current_l1), 0.1)

        # Active power total @ 0x5B14 (0.01 W units, signed)
        regs = self._read_holding(23316, 2)
        active_power_total = _decode_i32(regs) * 0.01
        expected = _read_attr(self._instance, "k__active_power_total_w")
        if expected is not None:
            self.assertAlmostEqual(active_power_total, expected, delta=50.0)
        else:
            self.assertLess(abs(active_power_total), 100000.0)

        # Frequency @ 0x5B2C (0.01 Hz units)
        regs = self._read_holding(23340, 1)
        frequency = regs[0] * 0.01
        self.assertGreater(frequency, 45.0)
        self.assertLess(frequency, 55.0)
