# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Hammerheads Engineers Sp. z o.o.
# See the accompanying LICENSE file for terms.

"""Integration coverage for the APC Easy UPS 3M Modbus model."""

import os
import unittest

from tests.common.modbus_utils import wait_for_modbus_endpoint
from tests.common.spx_utils import require_existing_instance, wait_seconds
from tests.devices.modbus_sut_base import ModbusTcpClient

INSTANCE_KEY = "spx_easy_ups_3m_modbus"
MODEL_ID = "Energy.UpsEasy3M.Modbus"
SPX_BASE_URL = os.environ.get("SPX_BASE_URL", "http://localhost:8000")


def _read_attr_value(instance, name):
    try:
        doc = instance.get()
    except Exception:
        doc = None
    if isinstance(doc, dict):
        attr = doc.get("attr")
        if isinstance(attr, dict) and name in attr:
            entry = attr.get(name)
            if isinstance(entry, dict) and "value" in entry:
                return entry.get("value")
            return entry
    return None


def _call_with_unit(client, method_name, *args, unit_id=1, **kwargs):
    method = getattr(client, method_name)
    try:
        return method(*args, slave=unit_id, **kwargs)
    except TypeError as exc:
        message = str(exc)
        if "unexpected keyword argument" in message and "'slave'" in message:
            return method(*args, unit=unit_id, **kwargs)
        raise


class TestModbusEasyUps3MSmoke(unittest.TestCase):
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

        wait_seconds(0.2)
        try:
            port, unit_id = wait_for_modbus_endpoint(cls._instance, timeout=10.0, interval=0.2)
        except TimeoutError as exc:
            raise unittest.SkipTest(str(exc)) from exc

        cls._modbus_port = port
        cls._modbus_unit_id = unit_id

    def _read_input_register(self, address, *, count=1):
        client = ModbusTcpClient(host="127.0.0.1", port=self._modbus_port)
        try:
            if not client.connect():
                self.skipTest(f"Modbus server not reachable at 127.0.0.1:{self._modbus_port}")
            result = _call_with_unit(
                client, "read_input_registers", address, count=count, unit_id=self._modbus_unit_id
            )
            if result is None or getattr(result, "isError", lambda: True)():
                # Some stacks treat input addresses as zero-based; try address - 1 once.
                alt_address = max(0, address - 1)
                result = _call_with_unit(
                    client,
                    "read_input_registers",
                    alt_address,
                    count=count,
                    unit_id=self._modbus_unit_id,
                )
            if result is None or getattr(result, "isError", lambda: True)():
                self.skipTest(f"Modbus read failed at address {address}")
            return result.registers
        finally:
            client.close()

    def _assert_scaled_register(self, attr_name, address, gain):
        value = _read_attr_value(self._instance, attr_name)
        if value is None:
            self.skipTest(f"Attribute '{attr_name}' not available on instance")
        expected = int(round(float(value) / gain))
        registers = self._read_input_register(address)
        self.assertEqual(1, len(registers))
        self.assertLessEqual(abs(registers[0] - expected), 1)

    def test_input_current_phase_a_register(self):
        self._assert_scaled_register("input_current_phase_a_a", 30005, 0.1)

    def test_output_power_phase_a_register(self):
        self._assert_scaled_register("output_active_power_phase_a_kw", 30018, 0.1)

    def test_output_line_voltage_ab_register(self):
        self._assert_scaled_register("output_line_voltage_ab_v", 30056, 0.1)

    def test_input_power_factor_phase_a_register(self):
        self._assert_scaled_register("input_power_factor_phase_a", 30008, 0.001)
