# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Hammerheads Engineers Sp. z o.o.
# See the accompanying LICENSE file for terms.

"""Shared integration coverage for the example SCPI power supply SUT implementation."""

import os
import unittest

from tests.common.ascii_utils import wait_for_ascii_port
from tests.common.spx_utils import bootstrap_model_instance, wait_seconds, wait_for_condition
from tests.common.repo import repo_root
from tests.devices.scpi_power_supply_sut_example import ScpiPowerSupplySUTExample


ROOT = repo_root()
MODEL_PATH = (
    ROOT
    / "library"
    / "domains"
    / "measurement_instruments"
    / "rigol"
    / "rigol_dp800__scpi.yaml"
)
MODEL_KEY = "tests__scpi_power_supply"
INSTANCE_KEY = "rigol_dp800_power_supply"
SPX_BASE_URL = os.environ.get("SPX_BASE_URL", "http://localhost:8000")


class TestScpiPowerSupplySUTExample(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import spx_python  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise unittest.SkipTest(f"spx_python not available: {exc}") from exc

        product_key = os.environ.get("SPX_PRODUCT_KEY")
        if not product_key:
            raise unittest.SkipTest(
                "SPX_PRODUCT_KEY must be set to run SCPI integration tests."
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
        self.instance = getattr(self.__class__, "_instance", None)
        if self.instance is None:  # pragma: no cover - defensive
            self.skipTest("SCPI power supply instance not initialised")

        try:
            comm = self.instance["communication"]["ascii"]
            attach = getattr(comm, "attach", None)
            if callable(attach):
                attach()
        except Exception:
            pass

        try:
            port = wait_for_ascii_port(self.instance, timeout=10.0, interval=0.2)
        except TimeoutError as exc:
            self.skipTest(str(exc))

        debug = bool(int(os.environ.get("SCPI_TEST_DEBUG", "1")))
        self.sut = ScpiPowerSupplySUTExample(port=port, debug=debug)
        try:
            connected = wait_for_condition(lambda: self.sut.connect(), timeout=5.0, interval=0.2)
        except OSError as exc:
            self.skipTest(f"Unable to connect to SCPI server on port {port}: {exc}")
        if not connected:
            self.skipTest(f"ASCII/SCPI server not reachable at 127.0.0.1:{port}")
        wait_seconds(0.2)

    def tearDown(self):
        if hasattr(self, "sut") and self.sut:
            self.sut.close()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _set_attribute(self, name: str, value) -> None:
        attrs = self.instance["attributes"]
        attrs[name].internal_value = value
        wait_seconds(0.1)

    def _get_attribute(self, name: str):
        return self.instance["attributes"][name].internal_value

    def _query_or_skip(self, command: str) -> str:
        reply = self.sut.query(command)
        if reply == "":
            self.skipTest(
                f"No response from SCPI server for command '{command}'."
            )
        return reply

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------
    def test_idn_contains_model(self):
        reply = self.sut.identify()
        self.assertIn("RIGOL", reply)
        self.assertIn("DP800", reply)

    def test_setpoints_roundtrip(self):
        channel = 1
        target_voltage = 12.5
        target_current = 0.8

        self.sut.set_voltage(channel, target_voltage)
        self.sut.set_current(channel, target_current)
        wait_seconds(0.2)

        self.assertAlmostEqual(self.sut.query_voltage_set(channel), target_voltage, places=2)
        self.assertAlmostEqual(self.sut.query_current_set(channel), target_current, places=3)

        self.assertAlmostEqual(self._get_attribute("k__ch1_voltage_set_v"), target_voltage, places=2)
        self.assertAlmostEqual(self._get_attribute("k__ch1_current_set_a"), target_current, places=3)

    def test_output_state_gates_measurements(self):
        channel = 1
        target_voltage = 6.6
        target_current = 0.25

        self.sut.set_voltage(channel, target_voltage)
        self.sut.set_current(channel, target_current)
        self.sut.output_off(channel)
        wait_seconds(0.2)

        self.assertEqual(self.sut.query_output_state(channel), "OFF")
        self.assertAlmostEqual(self.sut.measure_voltage(channel), 0.0, places=3)
        self.assertAlmostEqual(self.sut.measure_current(channel), 0.0, places=3)
        self.assertAlmostEqual(self.sut.measure_power(channel), 0.0, places=3)

        self.sut.output_on(channel)
        wait_seconds(0.2)

        self.assertEqual(self.sut.query_output_state(channel), "ON")
        self.assertAlmostEqual(self.sut.measure_voltage(channel), target_voltage, places=2)
        self.assertAlmostEqual(self.sut.measure_current(channel), target_current, places=3)
        self.assertAlmostEqual(self.sut.measure_power(channel), target_voltage * target_current, places=3)

    def test_query_voltage_alias(self):
        self._set_attribute("k__ch1_output_state", "ON")
        self._set_attribute("k__ch1_voltage_set_v", 9.1)
        self._set_attribute("k__ch1_current_set_a", 0.15)
        wait_seconds(0.2)
        raw = self._query_or_skip(":MEAS? CH1")
        self.assertAlmostEqual(float(raw), 9.1, places=2)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
