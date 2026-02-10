# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Hammerheads Engineers Sp. z o.o.
# See the accompanying LICENSE file for terms.

"""Integration coverage for the example Modbus Prevac XR40B-EC SUT device implementation."""

import os
import unittest

from tests.common.modbus_utils import wait_for_modbus_endpoint
from tests.common.spx_utils import (
    bootstrap_model_instance,
    wait_for_condition,
    wait_seconds,
)
from tests.common.repo import repo_root
from tests.devices.modbus_prevac_xr40b_ec_sut_example import (
    ModbusPrevacXR40BECExample,
    ModbusTcpClient,
)


ROOT = repo_root()
MODEL_PATH = (
    ROOT
    / "library"
    / "domains"
    / "iot"
    / "prevac"
    / "prevac_xr40b_ec__modbus.yaml"
)
MODEL_KEY = "tests__prevac_xr40b_ec"
INSTANCE_KEY = "prevac_xr40b_ec"
SPX_BASE_URL = os.environ.get("SPX_BASE_URL", "http://localhost:8000")


class TestModbusPrevacXR40BECExampleIntegration(unittest.TestCase):
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

        self.sut = ModbusPrevacXR40BECExample(
            host="127.0.0.1",
            port=port,
            unit_id=unit_id,
            timeout=1.0,
        )
        if not wait_for_condition(lambda: self.sut.connect(), timeout=5.0, interval=0.2):
            self.skipTest(
                f"Modbus server not reachable at 127.0.0.1:{port} (unit {unit_id})"
            )
        wait_seconds(0.2)

    def tearDown(self):
        if hasattr(self, "sut") and self.sut:
            self.sut.close()

    def test_read_status_and_measurements(self):
        status = self.sut.read_u16("status_word_1")
        voltage = self.sut.read_u16("emission_voltage_v")
        current = self.sut.read_float("emission_current_ma")

        self.assertIsInstance(status, int)
        self.assertGreaterEqual(status, 0)
        self.assertIsInstance(voltage, int)
        self.assertIsInstance(current, float)

    def test_write_voltage_setpoint(self):
        target = 1000
        self.sut.set_u16("k__emission_voltage_set_v", target)

        def _read_back() -> bool:
            try:
                value = int(self.sut.read_u16("k__emission_voltage_set_v"))
            except Exception:
                return False
            return value == target

        self.assertTrue(
            wait_for_condition(_read_back, timeout=5.0, interval=0.2),
            "Expected emission voltage setpoint to be writable and readable via Modbus",
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
