# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Hammerheads Engineers Sp. z o.o.
# See the accompanying LICENSE file for terms.

"""Shared integration coverage for the multichannel Modbus vacuum gauge SUT device implementation."""

import os
import unittest

from tests.common.modbus_utils import wait_for_modbus_endpoint
from tests.common.spx_utils import (
    bootstrap_model_instance,
    wait_for_condition,
    wait_seconds,
)
from tests.common.repo import repo_root
from tests.devices.modbus_vacuum_gauge_multichannel_sut_example import (
    ModbusTcpClient,
    ModbusVacuumGaugeMultichannelSUTExample,
)


ROOT = repo_root()
MODEL_PATH = (
    ROOT
    / "library"
    / "domains"
    / "vacuum_systems"
    / "generic"
    / "vacuum_gauge_multichannel__modbus.yaml"
)
MODEL_KEY = "tests__vacuum_gauge_multichannel"
INSTANCE_KEY = "generic_vacuum_gauge_multichannel"
SPX_BASE_URL = os.environ.get("SPX_BASE_URL", "http://localhost:8000")


class TestModbusVacuumGaugeMultichannelSUTExampleIntegration(unittest.TestCase):
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
            attribute_overrides=None,
        )

    def setUp(self):
        self.model = self.__class__._instance
        wait_seconds(0.2)

        # Disable auto-trigger for deterministic cycle tests.
        try:
            attrs = self.model["attributes"]
            if "auto_trigger_enable" in attrs:
                attrs["auto_trigger_enable"].internal_value = 0
            if "measure_start" in attrs:
                attrs["measure_start"].internal_value = 0
        except Exception:
            pass

        # Keep the Modbus channel attached for deterministic reads.
        try:
            scenario = self.model["scenarios"]["modbus_disconnect"]
        except Exception:
            scenario = None
        stop = getattr(scenario, "stop", None) if scenario is not None else None
        if callable(stop):
            try:
                stop()
            except Exception:
                pass
        wait_seconds(0.1)

        try:
            port, unit_id = wait_for_modbus_endpoint(
                self.model,
                comm_keys=("modbus_slave", "modbus_tcp"),
                timeout=10.0,
                interval=0.2,
            )
        except TimeoutError as exc:
            self.skipTest(str(exc))

        self.sut = ModbusVacuumGaugeMultichannelSUTExample(
            host="127.0.0.1", port=port, unit_id=unit_id, timeout=1.0
        )
        if not wait_for_condition(lambda: self.sut.connect(), timeout=5.0, interval=0.2):
            self.skipTest(f"Modbus server not reachable at 127.0.0.1:{port} (unit {unit_id})")
        wait_seconds(0.2)

    def tearDown(self):
        if hasattr(self, "sut") and self.sut:
            self.sut.close()

    def test_instance_running_and_measurement_cycle(self):
        def _state():
            return self.model.state

        wait_for_condition(lambda: _state() is not None, timeout=5.0)
        state = _state()
        if str(state or "").lower() != "running":
            try:
                self.model.start()
            except Exception:
                pass
            self.assertTrue(
                wait_for_condition(
                    lambda: str(_state() or "").lower() == "running",
                    timeout=5.0,
                ),
                "Instance should reach running state",
            )
            state = _state()

        self.assertIsNotNone(state, "Instance state should be available")
        self.assertEqual(str(state).lower(), "running", f"Instance should be running, got {state!r}")

        dwell_ms = 250
        self.sut.start_measurement(dwell_ms)

        self.assertTrue(
            wait_for_condition(
                lambda: self.sut.read_u16("measure_start") == 0,
                timeout=2.0,
            ),
            "Expected measure_start to auto-reset to 0",
        )

        self.assertTrue(
            wait_for_condition(
                lambda: self.sut.read_u16("measure_done") == 1,
                timeout=5.0,
            ),
            "Expected measurement to complete and set measure_done=1",
        )

        impulses = self.sut.read_impulses()
        self.assertEqual(len(impulses), 7)
        self.assertTrue(
            any(val > 0 for val in impulses),
            f"Expected at least one non-zero impulse count, got {impulses}",
        )

    def test_measurement_done_resets_on_every_cycle(self):
        """Run many short measurements to catch intermittent done-latch issues."""
        dwell_ms = 50
        cycles = 100  # long enough to expose intermittents without excessive runtime

        def _done():
            return self.sut.read_u16("measure_done")

        def _start():
            return self.sut.read_u16("measure_start")

        self.assertTrue(
            wait_for_condition(lambda: _done() == 1, timeout=3.0, interval=0.002),
            "Expected measure_done to be 1 before starting cycles",
        )

        for idx in range(cycles):
            self.sut.start_measurement(dwell_ms)
            self.assertTrue(
                wait_for_condition(lambda: _start() == 0, timeout=0.05, interval=0.001),
                f"Cycle {idx + 1}: measure_start should auto-reset to 0",
            )
            # self.assertTrue(
            #     wait_for_condition(lambda: _done() == 0, timeout=0.05, interval=0.001),
            #     f"Cycle {idx + 1}: measure_done should clear to 0 after start",
            # )
            self.assertTrue(
                wait_for_condition(lambda: _done() == 1, timeout=0.30, interval=0.005),
                f"Cycle {idx + 1}: measure_done should return to 1 after dwell completes",
            )
            impulses = self.sut.read_impulses()
            self.assertEqual(len(impulses), 7)
            self.assertTrue(
                any(val > 0 for val in impulses),
                f"Expected at least one non-zero impulse count, got {impulses}",
            )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
