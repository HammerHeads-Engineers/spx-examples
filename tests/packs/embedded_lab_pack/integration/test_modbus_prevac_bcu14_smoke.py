# SPDX-License-Identifier: MIT

import os
import unittest

from tests.common.modbus_utils import wait_for_modbus_endpoint
from tests.common.spx_utils import require_existing_instance, wait_for_condition, wait_seconds
from tests.devices.modbus_prevac_bcu14_sut_example import (
    ModbusPrevacBCU14SUTExample,
    ModbusTcpClient,
)


SPX_BASE_URL = os.environ.get("SPX_BASE_URL", "http://localhost:8000")
INSTANCE_KEY = "spx_prevac_bcu14"
MODEL_ID = "Process.ThermalController.PrevacBcu14.Modbus"


class TestModbusPrevacBCU14Smoke(unittest.TestCase):
    """Smoke coverage for the Prevac BCU14 Modbus TCP bakeout controller."""

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

        for action in (cls._instance.stop, cls._instance.reset, cls._instance.start):
            try:
                action()
            except Exception:
                pass

    def setUp(self):
        for comm_key in ("modbus_slave", "modbus_tcp"):
            try:
                comm = self._instance["communication"][comm_key]
            except Exception:
                continue
            attach = getattr(comm, "attach", None)
            if callable(attach):
                try:
                    attach()
                except Exception:
                    pass

        try:
            port, unit_id = wait_for_modbus_endpoint(self._instance, timeout=10.0, interval=0.2)
        except TimeoutError as exc:
            self.skipTest(str(exc))

        self._modbus_port = port
        self._modbus_unit_id = unit_id
        self.sut = ModbusPrevacBCU14SUTExample(
            host="127.0.0.1",
            port=port,
            unit_id=unit_id,
            timeout=1.0,
        )
        if not self.sut.connect():
            self.skipTest(f"Modbus server not reachable at 127.0.0.1:{port} (unit {unit_id})")

    def tearDown(self):
        if hasattr(self, "sut") and self.sut:
            self.sut.close()

    def test_zone1_target_write_and_temperature_response(self):
        baseline = self.sut.read_zone1_actual_temp()
        target = min(1200, baseline + 25)

        self.sut.set_zone1_target_temp(target)
        wait_seconds(0.2)
        self.assertEqual(self.sut.read_zone1_target_temp(), target)

        self.assertTrue(
            wait_for_condition(
                lambda: self.sut.read_zone1_actual_temp() >= baseline + 1,
                timeout=20.0,
                interval=0.5,
            ),
            "Expected zone 1 temperature to begin moving toward the target",
        )
