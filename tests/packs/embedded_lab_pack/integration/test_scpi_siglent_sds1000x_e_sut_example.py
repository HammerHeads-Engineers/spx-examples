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
    / "siglent"
    / "siglent_sds1000x_e__scpi.yaml"
)
MODEL_KEY = "tests__scpi_sds1000x_e"
INSTANCE_KEY = "siglent_sds1000x_e_oscilloscope"
SPX_BASE_URL = os.environ.get("SPX_BASE_URL", "http://localhost:8000")


class TestScpiSiglentSds1000xESutExample(unittest.TestCase):
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
            self.skipTest("Siglent SDS1000X-E instance not initialised")

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

    def _get_attribute(self, name: str):
        return self.instance["attributes"][name].internal_value

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
        target = "SIGLENT,SDS1000X-E,SDS1XE0000000,1.0"
        self._set_attribute("idn", target)
        reply = self._query_or_skip("*IDN?")
        self.assertEqual(reply, target)

    def test_measure_vpp_matches_attribute(self):
        target_vpp = 3.25
        self._set_attribute("channel1_vpp_v", target_vpp)
        raw = self._query_or_skip("C1:PAVA? PKPK")
        self.assertAlmostEqual(float(raw), target_vpp, places=2)

    def test_measure_vrms_matches_attribute(self):
        target_vrms = 1.12
        self._set_attribute("channel1_vrms_v", target_vrms)
        raw = self._query_or_skip("C1:PAVA? RMS")
        self.assertAlmostEqual(float(raw), target_vrms, places=2)

    def test_measure_vavg_matches_attribute(self):
        target_vavg = 0.15
        self._set_attribute("channel1_vavg_v", target_vavg)
        raw = self._query_or_skip("C1:PAVA? MEAN")
        self.assertAlmostEqual(float(raw), target_vavg, places=2)

    def test_measure_frequency_matches_attribute(self):
        target_freq = 1234.0
        self._set_attribute("channel1_freq_hz", target_freq)
        raw = self._query_or_skip("C1:PAVA? FREQ")
        self.assertAlmostEqual(float(raw), target_freq, places=1)

    def test_measure_period_matches_attribute(self):
        target_period = 0.00075
        self._set_attribute("channel1_period_s", target_period)
        raw = self._query_or_skip("C1:PAVA? PER")
        self.assertAlmostEqual(float(raw), target_period, places=5)

    def test_channel_scale_updates_attribute(self):
        reply = self._query_or_skip("C1:VDIV 0.5")
        self.assertEqual(reply, "OK")
        self.assertAlmostEqual(self._get_attribute("k__channel_1_scale_v"), 0.5, places=3)

    def test_channel_offset_updates_attribute(self):
        reply = self._query_or_skip("C1:OFST -0.25")
        self.assertEqual(reply, "OK")
        self.assertAlmostEqual(self._get_attribute("k__channel_1_offset_v"), -0.25, places=3)

    def test_timebase_updates_attribute(self):
        reply = self._query_or_skip("TDIV 0.0005")
        self.assertEqual(reply, "OK")
        self.assertAlmostEqual(self._get_attribute("k__timebase_scale_s"), 0.0005, places=6)

    def test_trigger_level_updates_attribute(self):
        reply = self._query_or_skip("TRLV 0.1")
        self.assertEqual(reply, "OK")
        self.assertAlmostEqual(self._get_attribute("k__trigger_level_v"), 0.1, places=3)


__all__ = ["TestScpiSiglentSds1000xESutExample"]
