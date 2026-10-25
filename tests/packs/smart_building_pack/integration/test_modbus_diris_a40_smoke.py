# SPDX-License-Identifier: MIT

from __future__ import annotations

import os
import unittest
from typing import Sequence

from tests.common.modbus_utils import wait_for_modbus_endpoint
from tests.common.spx_utils import require_existing_instance, wait_seconds
from tests.devices.modbus_sut_base import ModbusTcpClient, ModbusSUTBase

SPX_BASE_URL = os.environ.get("SPX_BASE_URL", "http://localhost:8000")
INSTANCE_KEY = "spx_energy_meter_diris_a40_modbus"
MODEL_ID = "Energy.EnergyMeterDirisA40.Modbus"


def _read_input_registers(client, address: int, count: int, unit_id: int) -> Sequence[int]:
    try:
        result = client.read_input_registers(address, count=count, slave=unit_id)
    except TypeError:
        result = client.read_input_registers(address, count=count, unit=unit_id)
    if result is None:
        raise RuntimeError(f"Modbus read returned no response at address {address}")
    if result.isError():
        raise RuntimeError(f"Modbus read failed at address {address}")
    return result.registers


def _decode_float(registers: Sequence[int]) -> float:
    return float(ModbusSUTBase.modbus_to_float(registers, "ABCD"))


def _decode_u32(registers: Sequence[int]) -> int:
    return int((int(registers[0]) << 16) | int(registers[1]))


def _attr_float(attributes, name: str) -> float:
    value = attributes[name].internal_value
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(value or 0.0)


class TestModbusDirisA40Smoke(unittest.TestCase):
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
            self.skipTest("DIRIS A-40 instance not initialised")
        self._instance = instance

        wait_seconds(0.2)

        try:
            port, unit_id = wait_for_modbus_endpoint(instance, timeout=10.0, interval=0.2)
        except TimeoutError as exc:
            self.skipTest(str(exc))

        self._modbus_port = port
        self._modbus_unit_id = unit_id

        self._client = ModbusTcpClient(host="127.0.0.1", port=port)
        if not self._client.connect():
            self.skipTest(f"Modbus server not reachable at 127.0.0.1:{port}")

    def tearDown(self):
        client = getattr(self, "_client", None)
        if client is not None:
            try:
                client.close()
            except Exception:
                pass

    def test_instantaneous_registers_match_model(self):
        attrs = self._instance["attributes"]

        freq_regs = _read_input_registers(self._client, 264, 2, self._modbus_unit_id)
        freq_hz = _decode_float(freq_regs)
        self.assertAlmostEqual(freq_hz, _attr_float(attrs, "k__frequency_hz"), delta=0.5)

        v1_regs = _read_input_registers(self._client, 284, 2, self._modbus_unit_id)
        v1 = _decode_float(v1_regs)
        self.assertAlmostEqual(v1, _attr_float(attrs, "k__voltage_l1_n_v"), delta=1.0)

        i1_regs = _read_input_registers(self._client, 308, 2, self._modbus_unit_id)
        i1 = _decode_float(i1_regs)
        self.assertAlmostEqual(i1, _attr_float(attrs, "k__current_l1_a"), delta=0.5)

        p1_regs = _read_input_registers(self._client, 344, 2, self._modbus_unit_id)
        p1_w = _decode_float(p1_regs)
        expected_p1_w = _attr_float(attrs, "active_power_l1_kw") * 1000.0
        self.assertAlmostEqual(p1_w, expected_p1_w, delta=200.0)

    def test_energy_registers_match_model(self):
        attrs = self._instance["attributes"]

        import_regs = _read_input_registers(self._client, 19843, 2, self._modbus_unit_id)
        export_regs = _read_input_registers(self._client, 19846, 2, self._modbus_unit_id)
        import_kwh = _decode_u32(import_regs)
        export_kwh = _decode_u32(export_regs)

        expected_import = int(round(max(0.0, _attr_float(attrs, "k__energy_import_total_kwh"))))
        expected_export = int(round(max(0.0, _attr_float(attrs, "k__energy_export_total_kwh"))))

        self.assertLessEqual(abs(import_kwh - expected_import), 1)
        self.assertLessEqual(abs(export_kwh - expected_export), 1)
