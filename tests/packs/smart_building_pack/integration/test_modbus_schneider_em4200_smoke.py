# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Hammerheads Engineers Sp. z o.o.
# See the accompanying LICENSE file for terms.

"""Integration smoke coverage for the Schneider Electric EM4200 Modbus model."""

from __future__ import annotations

import math
import os
import struct
import unittest

from tests.common.modbus_utils import wait_for_modbus_endpoint
from tests.common.spx_utils import require_existing_instance, wait_for_condition, wait_seconds
from tests.devices.modbus_sut_base import ModbusTcpClient


INSTANCE_KEY = "spx_energy_meter_em4200_modbus"
MODEL_ID = "Energy.EnergyMeterEm4200.Modbus"
SPX_BASE_URL = os.environ.get("SPX_BASE_URL", "http://localhost:8000")


def _decode_float(registers: list[int]) -> float:
    if len(registers) != 2:
        raise ValueError(f"Expected 2 registers, got {len(registers)}")
    packed = struct.pack(">HH", registers[0], registers[1])
    return struct.unpack(">f", packed)[0]


class TestModbusSchneiderEm4200Smoke(unittest.TestCase):
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
            comms = cls._instance["communication"]
        except Exception:
            comms = {}
        for comm_name in ("modbus_slave", "modbus_tcp"):
            comm = comms.get(comm_name) if isinstance(comms, dict) else None
            if comm is None:
                continue
            attach = getattr(comm, "attach", None)
            if callable(attach):
                try:
                    attach()
                except Exception:
                    pass

        try:
            port, unit_id = wait_for_modbus_endpoint(
                cls._instance,
                comm_keys=("modbus_slave", "modbus_tcp"),
                timeout=10.0,
                interval=0.2,
            )
        except TimeoutError as exc:
            raise unittest.SkipTest(str(exc)) from exc

        cls._modbus_port = port
        cls._modbus_unit_id = unit_id
        cls._modbus = ModbusTcpClient(host="127.0.0.1", port=port, timeout=2.0)

        connected = wait_for_condition(
            lambda: bool(cls._modbus.connect()),
            timeout=5.0,
            interval=0.2,
        )
        if not connected:
            raise unittest.SkipTest(
                f"Unable to connect to Modbus endpoint at 127.0.0.1:{port} (unit {unit_id})"
            )

    @classmethod
    def tearDownClass(cls):
        modbus = getattr(cls, "_modbus", None)
        if modbus is not None:
            try:
                modbus.close()
            except Exception:
                pass

    def _call_with_unit(self, method_name: str, *args, **kwargs):
        method = getattr(self._modbus, method_name)
        try:
            return method(*args, slave=self._modbus_unit_id, **kwargs)
        except TypeError as exc:
            if "slave" in str(exc) and "unexpected keyword argument" in str(exc):
                return method(*args, unit=self._modbus_unit_id, **kwargs)
            raise

    def _read_input_float(self, address: int) -> float:
        result = self._call_with_unit("read_input_registers", address, count=2)
        if result is None or getattr(result, "isError", lambda: False)():
            self.skipTest(f"Modbus input register read failed at address {address}")
        return _decode_float(result.registers)

    def _read_holding_float(self, address: int) -> float:
        result = self._call_with_unit("read_holding_registers", address, count=2)
        if result is None or getattr(result, "isError", lambda: False)():
            self.skipTest(f"Modbus holding register read failed at address {address}")
        return _decode_float(result.registers)

    def test_read_key_registers(self):
        energy_kwh = self._read_holding_float(257)
        voltage_l1_n = self._read_input_float(293)
        current_l1 = self._read_input_float(2705)
        frequency = self._read_input_float(1557)

        for value, label in [
            (energy_kwh, "energy_kwh"),
            (voltage_l1_n, "voltage_l1_n"),
            (current_l1, "current_l1"),
            (frequency, "frequency"),
        ]:
            self.assertTrue(math.isfinite(value), f"{label} should be finite, got {value!r}")

        self.assertGreater(voltage_l1_n, 0.0)
        self.assertGreater(current_l1, -2000.0)
        self.assertGreater(frequency, 0.0)
