# SPDX-License-Identifier: MIT

import os
import unittest

from tests.common.ascii_utils import wait_for_ascii_port
from tests.common.spx_utils import bootstrap_model_instance, wait_seconds, wait_for_condition
from tests.common.repo import repo_root
from tests.devices.scpi_electronic_load_sut_example import ScpiElectronicLoadSUTExample


ROOT = repo_root()
MODEL_PATH = (
    ROOT
    / "library"
    / "domains"
    / "measurement_instruments"
    / "siglent"
    / "siglent_sdl1000x__scpi.yaml"
)
MODEL_KEY = "tests__scpi_sdl1000x"
INSTANCE_KEY = "siglent_sdl1000x_electronic_load"
SPX_BASE_URL = os.environ.get("SPX_BASE_URL", "http://localhost:8000")


class TestScpiSiglentSdl1000xSutExample(unittest.TestCase):
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
            self.skipTest("Siglent SDL1000X instance not initialised")

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
        self.sut = ScpiElectronicLoadSUTExample(port=port, debug=debug)
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
        self.assertIn("SIGLENT", reply)
        self.assertIn("SDL", reply)

    def test_setpoints_roundtrip(self):
        self.sut.set_current(1.25)
        self.sut.set_voltage(12.0)
        self.sut.set_power(15.0)
        self.sut.set_resistance(8.0)
        wait_seconds(0.2)

        self.assertAlmostEqual(self.sut.current_setpoint(), 1.25, places=2)
        self.assertAlmostEqual(self.sut.voltage_setpoint(), 12.0, places=2)
        self.assertAlmostEqual(self.sut.power_setpoint(), 15.0, places=2)
        self.assertAlmostEqual(self.sut.resistance_setpoint(), 8.0, places=2)

        self.assertAlmostEqual(self._get_attribute("k__current_set_a"), 1.25, places=2)
        self.assertAlmostEqual(self._get_attribute("k__voltage_set_v"), 12.0, places=2)
        self.assertAlmostEqual(self._get_attribute("k__power_set_w"), 15.0, places=2)
        self.assertAlmostEqual(self._get_attribute("k__resistance_set_ohm"), 8.0, places=2)

    def test_mode_and_measurements(self):
        self.sut.set_mode("POWer")
        self.sut.set_voltage(10.0)
        self.sut.set_power(25.0)
        self.sut.input_on()
        wait_seconds(0.2)

        mode = self.sut.mode()
        self.assertEqual(mode, "POWER")
        self.assertEqual(self.sut.input_state(), 1)

        current = self.sut.measure_current()
        voltage = self.sut.measure_voltage()
        power = self.sut.measure_power()

        self.assertAlmostEqual(voltage, 10.0, places=2)
        self.assertAlmostEqual(power, 25.0, places=2)
        self.assertAlmostEqual(current, 2.5, places=2)

    def test_input_state_toggle(self):
        self.sut.input_on()
        wait_seconds(0.1)
        self.assertEqual(self.sut.input_state(), 1)
        self.assertEqual(self._get_attribute("k__input_state"), "ON")

        self.sut.input_off()
        wait_seconds(0.1)
        self.assertEqual(self.sut.input_state(), 0)
        self.assertEqual(self._get_attribute("k__input_state"), "OFF")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
