# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Hammerheads Engineers Sp. z o.o.
# See the accompanying LICENSE file for terms.

"""Integration coverage for the example Modbus Prevac M1600PDC-PS SUT device implementation."""

import os
import unittest

from tests.common.modbus_utils import wait_for_modbus_endpoint
from tests.common.spx_utils import (
    bootstrap_model_instance,
    wait_for_condition,
    wait_seconds,
)
from tests.common.repo import repo_root
from tests.devices.modbus_prevac_m1600pdc_ps_sut_example import (
    ModbusPrevacM1600PDCPSExample,
    ModbusTcpClient,
)


ROOT = repo_root()
MODEL_PATH = (
    ROOT
    / "library"
    / "domains"
    / "iot"
    / "prevac"
    / "prevac_m1600pdc_ps__modbus.yaml"
)
MODEL_KEY = "tests__prevac_m1600pdc_ps"
INSTANCE_KEY = "prevac_m1600pdc_ps"
SPX_BASE_URL = os.environ.get("SPX_BASE_URL", "http://localhost:8000")


class TestModbusPrevacM1600PDCPSExampleIntegration(unittest.TestCase):
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
            raise unittest.SkipTest(
                "SPX_PRODUCT_KEY must be set to run integration tests."
            )

        cls._spx = spx_python
        (
            cls._client,
            cls._instance,
            cls._model_changed,
        ) = bootstrap_model_instance(
            spx_python,
            product_key=product_key,
            base_url=SPX_BASE_URL,
            model_path=MODEL_PATH,
            model_key=MODEL_KEY,
            instance_key=INSTANCE_KEY,
        )

    def setUp(self):
        self.model = self.__class__._instance
        wait_seconds(0.2)

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
                comm_keys=("modbus_slave", "modbus_tcp"),
                timeout=10.0,
                interval=0.2,
            )
        except TimeoutError as exc:
            self.skipTest(str(exc))

        self.sut = ModbusPrevacM1600PDCPSExample(
            host="127.0.0.1",
            port=port,
            unit_id=unit_id,
            timeout=1.0,
        )
        if not wait_for_condition(lambda: self.sut.connect(), timeout=5.0, interval=0.2):
            self.skipTest(f"Modbus server not reachable at 127.0.0.1:{port} (unit {unit_id})")
        wait_seconds(0.2)

    def tearDown(self):
        if hasattr(self, "sut") and self.sut:
            self.sut.close()

    def test_read_status_and_measurements(self):
        state = self.sut.read_u16("device_state")
        power = self.sut.read_float("magnetron_power_w")
        voltage = self.sut.read_float("magnetron_voltage_v")
        current = self.sut.read_float("magnetron_current_ma")

        self.assertIsInstance(state, int)
        self.assertGreaterEqual(state, 0)
        for value in (power, voltage, current):
            self.assertIsInstance(value, float)

    def test_write_power_setpoint(self):
        target = 220.0
        self.sut.set_float("power_set_w", target)

        def _read_back() -> bool:
            try:
                value = float(self.sut.read_float("power_set_w"))
            except Exception:
                return False
            return abs(value - target) < 0.1

        self.assertTrue(
            wait_for_condition(_read_back, timeout=5.0, interval=0.2),
            "Expected power setpoint to be writable and readable via Modbus",
        )

    def test_write_frequency_setpoint(self):
        target = 123.0
        self.sut.set_float("frequency_khz", target)

        def _read_back() -> bool:
            try:
                value = float(self.sut.read_float("frequency_khz"))
            except Exception:
                return False
            return abs(value - target) < 0.1

        self.assertTrue(
            wait_for_condition(_read_back, timeout=5.0, interval=0.2),
            "Expected frequency setpoint to be writable and readable via Modbus",
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
