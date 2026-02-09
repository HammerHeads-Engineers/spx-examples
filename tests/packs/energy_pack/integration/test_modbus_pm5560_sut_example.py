# SPDX-License-Identifier: MIT

import os
import unittest

from tests.common.modbus_utils import wait_for_modbus_endpoint
from tests.common.spx_utils import require_existing_instance, wait_for_condition, wait_seconds
from tests.devices.modbus_sut_base import ModbusSUTBase, ModbusTcpClient


SPX_BASE_URL = os.environ.get("SPX_BASE_URL", "http://localhost:8000")
INSTANCE_KEY = "spx_energy_meter_pm5560_modbus"
MODEL_ID = "Energy.EnergyMeterPm5560.Modbus"


class TestModbusPm5560SUTExampleIntegration(unittest.TestCase):
    """Smoke test the PM5560 Modbus map via an installer-created instance."""

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

        cls._spx = spx_python
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
        wait_seconds(0.2)

        # Ensure the Modbus adapter is attached before talking to it.
        try:
            comm = self._instance["communication"]["modbus_slave"]
        except Exception:
            comm = None
        attach = getattr(comm, "attach", None)
        if callable(attach):
            try:
                attach()
            except Exception:
                pass

        try:
            port, unit_id = wait_for_modbus_endpoint(
                self._instance,
                comm_keys=("modbus_slave", "modbus_tcp"),
                timeout=10.0,
                interval=0.2,
            )
        except TimeoutError as exc:
            self.skipTest(str(exc))

        self._modbus_port = port
        self._modbus_unit_id = unit_id

        self._client = ModbusTcpClient(host="127.0.0.1", port=port, timeout=1.0)
        if not wait_for_condition(lambda: self._client.connect(), timeout=5.0, interval=0.2):
            self.skipTest(
                f"Modbus server not reachable at 127.0.0.1:{port} (unit {unit_id})"
            )

    def tearDown(self):
        if getattr(self, "_client", None):
            try:
                self._client.close()
            except Exception:
                pass

    def _read_input_float(self, address: int) -> float:
        result = self._call_modbus("read_input_registers", address, count=2)
        if result is None or result.isError():  # pragma: no cover - delegated to pymodbus
            raise RuntimeError(f"Modbus input read failed at address {address}")
        return ModbusSUTBase.modbus_to_float(result.registers, "ABCD")

    def _call_modbus(self, method_name: str, *args, **kwargs):
        method = getattr(self._client, method_name)
        try:
            return method(*args, slave=self._modbus_unit_id, **kwargs)
        except TypeError as exc:
            message = str(exc)
            if "unexpected keyword argument" in message and "'slave'" in message:
                return method(*args, unit=self._modbus_unit_id, **kwargs)
            raise

    def test_reads_voltage_power_and_frequency(self):
        voltage_l1_n = self._read_input_float(3028)
        active_power_total = self._read_input_float(3060)
        frequency_hz = self._read_input_float(3110)

        self.assertGreater(voltage_l1_n, 0.0)
        self.assertGreaterEqual(active_power_total, 0.0)
        self.assertGreater(frequency_hz, 0.0)
