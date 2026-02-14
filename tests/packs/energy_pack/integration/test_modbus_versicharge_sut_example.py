# SPDX-License-Identifier: MIT

import os
import unittest

from tests.common.modbus_utils import wait_for_modbus_endpoint
from tests.common.spx_utils import require_existing_instance, wait_for_condition, wait_seconds
from tests.devices.modbus_versicharge_sut_example import (
    ModbusTcpClient,
    ModbusVersiChargeAcSUTExample,
)


SPX_BASE_URL = os.environ.get("SPX_BASE_URL", "http://localhost:8000")
INSTANCE_KEY = "spx_evse_versicharge_ac_modbus"
MODEL_ID = "Energy.EVSE.SiemensVersiChargeAc.Modbus"


class TestModbusVersiChargeSUTExampleIntegration(unittest.TestCase):
    """Smoke test the Siemens VersiCharge Modbus map via an installer-created instance."""

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

        self._sut = ModbusVersiChargeAcSUTExample(
            host="127.0.0.1",
            port=port,
            unit_id=unit_id,
            timeout=1.0,
        )
        if not wait_for_condition(self._sut.connect, timeout=5.0, interval=0.2):
            self.skipTest(
                f"Modbus server not reachable at 127.0.0.1:{port} (unit {unit_id})"
            )

    def tearDown(self):
        if getattr(self, "_sut", None):
            try:
                self._sut.close()
            except Exception:
                pass

    def test_reads_charge_metrics(self):
        voltage_l1 = self._sut.read_voltage_l1()
        current_l1 = self._sut.read_current_l1()
        active_power_sum = self._sut.read_active_power_sum()
        power_factor_sum = self._sut.read_power_factor_sum()
        energy_consumed = self._sut.read_energy_consumed_kwh()

        self.assertGreater(voltage_l1, 0.0)
        self.assertGreaterEqual(current_l1, 0.0)
        self.assertGreaterEqual(active_power_sum, 0.0)
        self.assertGreaterEqual(power_factor_sum, 0.0)
        self.assertGreaterEqual(energy_consumed, 0.0)

    def test_writes_max_current(self):
        target_current = 12
        self._sut.write_max_charging_current(target_current)
        wait_seconds(0.2)
        read_current = self._sut.read_max_charging_current()
        self.assertAlmostEqual(read_current, float(target_current), delta=0.5)
