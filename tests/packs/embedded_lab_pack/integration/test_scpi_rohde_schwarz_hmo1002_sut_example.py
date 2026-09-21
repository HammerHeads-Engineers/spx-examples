# SPDX-License-Identifier: MIT

import os
import unittest

from tests.common.ascii_utils import wait_for_ascii_port
from tests.common.spx_utils import bootstrap_model_instance, wait_seconds, wait_for_condition
from tests.common.repo import repo_root
from tests.devices.scpi_oscilloscope_sut_example import ScpiOscilloscopeSUTExample


ROOT = repo_root()
MODEL_PATH = (
    ROOT
    / "library"
    / "domains"
    / "measurement_instruments"
    / "rohde_schwarz"
    / "rohde_schwarz_hmo1002__scpi.yaml"
)
MODEL_KEY = "tests__scpi_rohde_schwarz_hmo1002"
INSTANCE_KEY = "rohde_schwarz_hmo1002_oscilloscope"
SPX_BASE_URL = os.environ.get("SPX_BASE_URL", "http://localhost:8000")


class TestScpiRohdeSchwarzHmo1002SutExample(unittest.TestCase):
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
            self.skipTest("Rohde & Schwarz HMO1002 instance not initialised")

        self._ensure_scenario_stopped("amplitude_sweep")
        wait_seconds(0.1)

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
        self.sut = ScpiOscilloscopeSUTExample(port=port, debug=debug)
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

    def _ensure_scenario_stopped(self, name: str) -> None:
        try:
            scenario = self.instance["scenarios"][name]
        except Exception:
            return
        stop = getattr(scenario, "stop", None)
        if callable(stop):
            try:
                stop()
            except Exception:
                return
            wait_seconds(0.1)

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
        target = "Rohde&Schwarz,HMO1002,0000000000,1.00"
        self._set_attribute("idn", target)
        reply = self._query_or_skip("*IDN?")
        self.assertEqual(reply, target)

    def test_measure_vpp_matches_attribute(self):
        target_vpp = 3.25
        self._set_attribute("channel1_vpp_v", target_vpp)
        vpp = self.sut.measure_vpp()
        self.assertAlmostEqual(vpp, target_vpp, places=2)

    def test_measure_vrms_matches_attribute(self):
        target_vpp = 3.12
        expected_vrms = target_vpp * 0.353553
        self._set_attribute("channel1_vpp_v", target_vpp)
        wait_seconds(0.2)
        vrms = self.sut.measure_vrms()
        self.assertAlmostEqual(vrms, expected_vrms, places=2)

    def test_measure_vavg_matches_attribute(self):
        target_vavg = 0.25
        self._set_attribute("channel1_vavg_v", target_vavg)
        vavg = self.sut.measure_vavg()
        self.assertAlmostEqual(vavg, target_vavg, places=2)

    def test_measure_frequency_matches_attribute(self):
        target_freq = 1100.0
        self._set_attribute("channel1_freq_hz", target_freq)
        freq = self.sut.measure_frequency()
        self.assertAlmostEqual(freq, target_freq, places=1)

    def test_measure_period_matches_attribute(self):
        target_freq = 1250.0
        expected_period = 1.0 / target_freq
        self._set_attribute("channel1_freq_hz", target_freq)
        wait_seconds(0.2)
        period = self.sut.measure_period()
        self.assertAlmostEqual(period, expected_period, places=5)


__all__ = ["TestScpiRohdeSchwarzHmo1002SutExample"]
