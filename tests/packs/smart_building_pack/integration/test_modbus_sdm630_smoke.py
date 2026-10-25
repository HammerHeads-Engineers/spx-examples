# SPDX-License-Identifier: MIT

from __future__ import annotations

import os
import unittest
from typing import Sequence

from tests.common.modbus_utils import wait_for_modbus_endpoint
from tests.common.spx_utils import require_existing_instance, wait_seconds
from tests.devices.modbus_sut_base import ModbusTcpClient, ModbusSUTBase

SPX_BASE_URL = os.environ.get("SPX_BASE_URL", "http://localhost:8000")
INSTANCE_KEY = "spx_energy_meter_sdm630_modbus"
MODEL_ID = "Energy.EnergyMeterEastronSdm630.Modbus"


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


def _attr_float(attributes, name: str) -> float:
    value = attributes[name].internal_value
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(value or 0.0)


def _set_attribute(attributes, name: str, value: float) -> None:
    attributes[name].internal_value = value


class TestModbusSdm630Smoke(unittest.TestCase):
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
            self.skipTest("SDM630 instance not initialised")
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
        _set_attribute(attrs, "k__voltage_l1_n_v", 231.5)
        _set_attribute(attrs, "k__current_l1_a", 9.25)
        _set_attribute(attrs, "k__frequency_hz", 49.9)
        wait_seconds(0.2)

        v1_regs = _read_input_registers(self._client, 0, 2, self._modbus_unit_id)
        v1 = _decode_float(v1_regs)
        self.assertAlmostEqual(v1, _attr_float(attrs, "k__voltage_l1_n_v"), delta=0.2)

        i1_regs = _read_input_registers(self._client, 6, 2, self._modbus_unit_id)
        i1 = _decode_float(i1_regs)
        self.assertAlmostEqual(i1, _attr_float(attrs, "k__current_l1_a"), delta=0.05)

        freq_regs = _read_input_registers(self._client, 70, 2, self._modbus_unit_id)
        freq_hz = _decode_float(freq_regs)
        self.assertAlmostEqual(freq_hz, _attr_float(attrs, "k__frequency_hz"), delta=0.2)

        power_regs = _read_input_registers(self._client, 52, 2, self._modbus_unit_id)
        total_w = _decode_float(power_regs)
        self.assertAlmostEqual(
            total_w,
            _attr_float(attrs, "active_power_total_w"),
            delta=50.0,
        )

    def test_energy_registers_match_model(self):
        attrs = self._instance["attributes"]
        _set_attribute(attrs, "energy_import_total_kwh", 123.4)
        _set_attribute(attrs, "energy_export_total_kwh", 4.2)
        wait_seconds(0.2)

        import_regs = _read_input_registers(self._client, 72, 2, self._modbus_unit_id)
        export_regs = _read_input_registers(self._client, 74, 2, self._modbus_unit_id)
        import_kwh = _decode_float(import_regs)
        export_kwh = _decode_float(export_regs)

        self.assertAlmostEqual(import_kwh, _attr_float(attrs, "energy_import_total_kwh"), delta=0.2)
        self.assertAlmostEqual(export_kwh, _attr_float(attrs, "energy_export_total_kwh"), delta=0.2)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
