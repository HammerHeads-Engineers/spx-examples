# SPDX-License-Identifier: MIT

import os
import unittest

from tests.common.ascii_utils import wait_for_ascii_port
from tests.common.spx_utils import bootstrap_model_instance, wait_seconds, wait_for_condition
from tests.common.repo import repo_root
from tests.devices.scpi_rohde_schwarz_hmp4040_sut_example import (
    ScpiRohdeSchwarzHmp4040SUTExample,
)


ROOT = repo_root()
MODEL_PATH = (
    ROOT
    / "library"
    / "domains"
    / "measurement_instruments"
    / "rohde_schwarz"
    / "rohde_schwarz_hmp4040__scpi.yaml"
)
MODEL_KEY = "tests__scpi_hmp4040"
INSTANCE_KEY = "rohde_schwarz_hmp4040_power_supply"
SPX_BASE_URL = os.environ.get("SPX_BASE_URL", "http://localhost:8000")


class TestScpiRohdeSchwarzHmp4040SutExample(unittest.TestCase):
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
            self.skipTest("HMP4040 instance not initialised")

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
        self.sut = ScpiRohdeSchwarzHmp4040SUTExample(port=port, debug=debug)
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
    def _get_attribute(self, name: str):
        return self.instance["attributes"][name].internal_value

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------
    def test_idn_contains_model(self):
        reply = self.sut.identify()
        self.assertIn("Rohde&Schwarz", reply)
        self.assertIn("HMP", reply)

    def test_channel_selection(self):
        self.sut.select_output(2)
        self.sut.drain()
        wait_seconds(0.1)
        self.assertEqual(self.sut.selected_output(), 2)
        self.assertEqual(self._get_attribute("k__selected_channel"), 2)

    def test_setpoints_roundtrip(self):
        self.sut.select_output(2)
        self.sut.set_voltage(7.2)
        self.sut.set_current(1.35)
        self.sut.drain()
        wait_seconds(0.2)

        self.assertAlmostEqual(self.sut.voltage_setpoint(), 7.2, places=2)
        self.assertAlmostEqual(self.sut.current_setpoint(), 1.35, places=2)

        self.assertAlmostEqual(self._get_attribute("k__ch2_voltage_set_v"), 7.2, places=2)
        self.assertAlmostEqual(self._get_attribute("k__ch2_current_set_a"), 1.35, places=2)

    def test_output_and_measurements(self):
        self.sut.select_output(3)
        self.sut.output_on()
        self.sut.set_voltage(12.5)
        self.sut.set_current(0.8)
        self.sut.drain()
        wait_seconds(0.2)

        self.assertEqual(self.sut.output_state(), 1)
        self.assertEqual(self._get_attribute("k__ch3_output_state"), 1)

        voltage = self.sut.measure_voltage()
        current = self.sut.measure_current()
        power = self.sut.measure_power()

        self.assertAlmostEqual(voltage, 12.5, places=2)
        self.assertAlmostEqual(current, 0.8, places=2)
        self.assertAlmostEqual(power, 10.0, places=2)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
