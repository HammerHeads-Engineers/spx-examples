# SPDX-License-Identifier: MIT

"""Smoke test for the Schneider Electric PowerLogic PM8000 Modbus model."""

from __future__ import annotations

import os
import struct
import unittest

from tests.common.modbus_utils import wait_for_modbus_endpoint
from tests.common.spx_utils import require_existing_instance, wait_for_condition
from tests.devices.modbus_sut_base import ModbusTcpClient

INSTANCE_KEY = "spx_energy_meter_pm8000_modbus"
MODEL_ID = "Energy.EnergyMeterPm8000.Modbus"
SPX_BASE_URL = os.environ.get("SPX_BASE_URL", "http://localhost:8000")


def _decode_float_abcd(registers: list[int]) -> float:
    if len(registers) < 2:
        raise ValueError(f"Expected 2 registers, got {len(registers)}")
    return struct.unpack(">f", struct.pack(">HH", registers[0], registers[1])
    )[0]


def _call_with_unit_kwarg(client, method_name: str, *args, unit_id: int, **kwargs):
    method = getattr(client, method_name)
    try:
        return method(*args, slave=unit_id, **kwargs)
    except TypeError as exc:
        if "unexpected keyword argument" in str(exc) and "'slave'" in str(exc):
            return method(*args, unit=unit_id, **kwargs)
        raise


class TestModbusPm8000Smoke(unittest.TestCase):
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

    def setUp(self):
        instance = getattr(self.__class__, "_instance", None)
        if instance is None:  # pragma: no cover - defensive
            self.skipTest("PM8000 instance not initialised")

        try:
            port, unit_id = wait_for_modbus_endpoint(instance, timeout=10.0, interval=0.2)
        except TimeoutError as exc:
            self.skipTest(str(exc))

        self._modbus_port = port
        self._modbus_unit_id = unit_id

    def _connect_client(self):
        client = ModbusTcpClient(host="127.0.0.1", port=self._modbus_port)
        if not wait_for_condition(client.connect, timeout=5.0, interval=0.2):
            self.skipTest(
                f"Modbus server not reachable at 127.0.0.1:{self._modbus_port} (unit {self._modbus_unit_id})"
            )
        return client

    def test_reads_current_avg_register(self):
        client = self._connect_client()
        try:
            result = _call_with_unit_kwarg(
                client,
                "read_input_registers",
                3010,
                count=2,
                unit_id=self._modbus_unit_id,
            )
            if result is None or getattr(result, "isError", lambda: True)():
                self.fail("Modbus read_input_registers failed for PM8000 current_avg")
            value = _decode_float_abcd(result.registers)
            self.assertTrue(
                value == value,  # NaN check
                "Decoded current_avg value is NaN",
            )
        finally:
            client.close()
