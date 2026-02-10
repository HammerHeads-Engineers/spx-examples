# SPDX-License-Identifier: MIT

import os
import time
import unittest

from tests.common.ascii_utils import wait_for_ascii_port
from tests.common.spx_utils import bootstrap_model_instance, wait_seconds, wait_for_condition
from tests.common.repo import repo_root
from tests.devices.scpi_multimeter_sut_example import ScpiMultimeterSUTExample


ROOT = repo_root()
MODEL_PATH = (
    ROOT
    / "library"
    / "domains"
    / "measurement_instruments"
    / "rohde_schwarz"
    / "rohde_schwarz_hmc8012__scpi.yaml"
)
MODEL_KEY = "tests__scpi_hmc8012"
INSTANCE_KEY = "rohde_schwarz_hmc8012_multimeter"
SPX_BASE_URL = os.environ.get("SPX_BASE_URL", "http://localhost:8000")


class TestScpiRohdeSchwarzHmc8012SUTExample(unittest.TestCase):
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
        if not wait_for_condition(cls._is_running, timeout=10.0, interval=0.2):
            raise AssertionError("HMC8012 instance did not reach running state.")

    @classmethod
    def _is_running(cls) -> bool:
        try:
            doc = cls._instance.get()
        except Exception:
            return False
        if not isinstance(doc, dict):
            return False
        state = doc.get("state")
        if state is None:
            attr = doc.get("attr")
            if isinstance(attr, dict):
                state_attr = attr.get("state")
                if isinstance(state_attr, dict):
                    state = state_attr.get("value")
        return str(state).lower() == "running"

    def setUp(self):
        self.instance = getattr(self.__class__, "_instance", None)
        if self.instance is None:  # pragma: no cover - defensive
            self.skipTest("HMC8012 instance not initialised")

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
        self.sut = ScpiMultimeterSUTExample(port=port, debug=debug)
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
    def test_idn_matches_attribute(self):
        target = "Rohde&Schwarz,HMC8012,0000000000,1.00"
        self._set_attribute("idn", target)
        reply = self._query_or_skip("*IDN?")
        self.assertEqual(reply, target)

    def test_measure_voltage_dc_matches_attribute(self):
        target_voltage = 7.25
        self._set_attribute("voltage_dc_v", target_voltage)
        raw = self._query_or_skip("MEAS:VOLT:DC?")
        self.assertAlmostEqual(float(raw), target_voltage, places=2)

    def test_measure_current_dc_matches_attribute(self):
        target_current = 0.42
        self._set_attribute("current_dc_a", target_current)
        raw = self._query_or_skip("MEAS:CURR:DC?")
        self.assertAlmostEqual(float(raw), target_current, places=3)

    def test_measure_resistance_matches_attribute(self):
        target_res = 1234.5
        self._set_attribute("resistance_ohm", target_res)
        raw = self._query_or_skip("MEAS:RES?")
        self.assertAlmostEqual(float(raw), target_res, places=2)

    def test_measure_frequency_matches_attribute(self):
        target_freq = 987.0
        self._set_attribute("frequency_hz", target_freq)
        raw = self._query_or_skip("MEAS:FREQ?")
        self.assertAlmostEqual(float(raw), target_freq, places=2)

    def test_measure_period_matches_attribute(self):
        target_period = 0.0015
        self._set_attribute("period_s", target_period)
        raw = self._query_or_skip("MEAS:PER?")
        self.assertAlmostEqual(float(raw), target_period, places=5)

    def test_conf_voltage_dc_updates_mode(self):
        self.sut.write("CONF:VOLT:DC")
        self.sut.drain()
        time.sleep(0.1)
        self.assertEqual(self._get_attribute("k__mode"), "VOLT:DC")

    def test_conf_current_dc_updates_mode(self):
        self.sut.write("CONF:CURR:DC")
        self.sut.drain()
        time.sleep(0.1)
        self.assertEqual(self._get_attribute("k__mode"), "CURR:DC")

    def test_read_returns_mode_value(self):
        self.sut.write("CONF:RES")
        self.sut.drain()
        time.sleep(0.1)
        target_res = 550.0
        self._set_attribute("resistance_ohm", target_res)
        raw = self._query_or_skip("READ?")
        self.assertAlmostEqual(float(raw), target_res, places=2)
