# SPDX-License-Identifier: MIT

import os
import unittest

from tests.common.modbus_utils import wait_for_modbus_endpoint
from tests.common.spx_utils import require_existing_instance, wait_for_condition, wait_seconds

try:
    from pymodbus.client import ModbusTcpClient  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    try:
        from pymodbus.client.sync import ModbusTcpClient  # type: ignore
    except Exception:  # pragma: no cover - optional dependency
        ModbusTcpClient = None  # type: ignore


SPX_BASE_URL = os.environ.get("SPX_BASE_URL", "http://localhost:8000")
INSTANCE_KEY = "spx_energy_meter_diris_a40_modbus"
MODEL_ID = "Energy.EnergyMeterDirisA40.Modbus"

FREQ_ADDR = 18436
VOLTAGE_L1N_ADDR = 18624
ACTIVE_POWER_TOTAL_ADDR = 18460
SCALE_0P01 = 100.0


def _decode_u32(registers):
    return (int(registers[0]) << 16) | int(registers[1])


def _decode_int32(registers):
    value = _decode_u32(registers)
    if value >= 0x80000000:
        return value - 0x100000000
    return value


def _read_attr_value(instance, name):
    try:
        attr = instance["attributes"][name]
        value = getattr(attr, "internal_value", attr)
    except Exception:
        value = None
    return value


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

    def setUp(self):
        self.model = self.__class__._instance

        try:
            self.model.stop()
        except Exception:
            pass
        try:
            self.model.reset()
        except Exception:
            pass
        try:
            self.model.start()
        except Exception:
            pass

        wait_seconds(0.3)

        try:
            comm = self.model["communication"]["modbus_slave"]
            attach = getattr(comm, "attach", None)
            if callable(attach):
                attach()
        except Exception:
            pass

        try:
            port, unit_id = wait_for_modbus_endpoint(
                self.model,
                comm_keys=("modbus_slave",),
                timeout=10.0,
                interval=0.2,
            )
        except TimeoutError as exc:
            self.skipTest(str(exc))

        self.port = port
        self.unit_id = unit_id
        self.client = ModbusTcpClient(host="127.0.0.1", port=port, timeout=1.0)
        if not wait_for_condition(lambda: self.client.connect(), timeout=5.0, interval=0.2):
            self.skipTest(f"Modbus server not reachable at 127.0.0.1:{port} (unit {unit_id})")

    def tearDown(self):
        if hasattr(self, "client") and self.client:
            self.client.close()

    def _read_input_registers(self, address, count=2):
        try:
            result = self.client.read_input_registers(address, count=count, slave=self.unit_id)
        except TypeError:
            result = self.client.read_input_registers(address, count=count, unit=self.unit_id)
        if result is None:
            raise RuntimeError(f"No Modbus response at address {address}")
        if result.isError():  # pragma: no cover - delegated to pymodbus
            raise RuntimeError(f"Modbus read error at address {address}")
        return result.registers

    def test_frequency_voltage_power_registers(self):
        wait_seconds(0.3)

        freq_raw = _decode_u32(self._read_input_registers(FREQ_ADDR))
        voltage_raw = _decode_u32(self._read_input_registers(VOLTAGE_L1N_ADDR))
        power_raw = _decode_int32(self._read_input_registers(ACTIVE_POWER_TOTAL_ADDR))

        freq_hz = float(_read_attr_value(self.model, "k__frequency_hz") or 0.0)
        voltage_v = float(_read_attr_value(self.model, "k__voltage_l1_n_v") or 0.0)
        power_w = float(_read_attr_value(self.model, "k__active_power_total_w") or 0.0)

        expected_freq = int(round(freq_hz * SCALE_0P01))
        expected_voltage = int(round(voltage_v * SCALE_0P01))
        expected_power = int(round(power_w))

        self.assertAlmostEqual(freq_raw, expected_freq, delta=2)
        self.assertAlmostEqual(voltage_raw, expected_voltage, delta=5)
        self.assertAlmostEqual(power_raw, expected_power, delta=10)
