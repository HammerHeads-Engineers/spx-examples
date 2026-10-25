# SPDX-License-Identifier: MIT

import os
import unittest

from tests.common.ascii_utils import wait_for_ascii_port
from tests.common.spx_utils import bootstrap_model_instance, wait_seconds, wait_for_condition
from tests.common.repo import repo_root
from tests.devices.scpi_spectrum_analyzer_sut_example import ScpiSpectrumAnalyzerSUTExample


ROOT = repo_root()
MODEL_PATH = (
    ROOT
    / "library"
    / "domains"
    / "measurement_instruments"
    / "siglent"
    / "siglent_ssa3000x__scpi.yaml"
)
MODEL_KEY = "tests__scpi_ssa3000x"
INSTANCE_KEY = "siglent_ssa3000x_spectrum_analyzer"
SPX_BASE_URL = os.environ.get("SPX_BASE_URL", "http://localhost:8000")


class TestScpiSiglentSsa3000xSutExample(unittest.TestCase):
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
            self.skipTest("Siglent SSA3000X instance not initialised")

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
        self.sut = ScpiSpectrumAnalyzerSUTExample(port=port, debug=debug)
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
        target = "SIGLENT,SSA3000X,SSA3X0000000,1.0"
        self._set_attribute("idn", target)
        reply = self._query_or_skip("*IDN?")
        self.assertEqual(reply, target)

    def test_center_frequency_query_matches_attribute(self):
        target = 1_500_000_000.0
        self._set_attribute("k__center_frequency_hz", target)
        raw = self._query_or_skip(":SENSe:FREQuency:CENTer?")
        self.assertAlmostEqual(float(raw), target, places=2)

    def test_center_frequency_set_updates_attribute(self):
        reply = self._query_or_skip(":SENSe:FREQuency:CENTer 2200000000")
        self.assertEqual(reply, "OK")
        self.assertAlmostEqual(self._get_attribute("k__center_frequency_hz"), 2_200_000_000.0, places=2)

    def test_span_set_updates_attribute(self):
        reply = self._query_or_skip(":SENSe:FREQuency:SPAN 40000000")
        self.assertEqual(reply, "OK")
        self.assertAlmostEqual(self._get_attribute("k__span_hz"), 40_000_000.0, places=2)

    def test_reference_level_set_updates_attribute(self):
        reply = self._query_or_skip(":DISPlay:WINDow:TRACe:Y:SCALe:RLEVel -10")
        self.assertEqual(reply, "OK")
        self.assertAlmostEqual(self._get_attribute("k__reference_level_dbm"), -10.0, places=2)

    def test_marker_state_updates_attribute(self):
        reply = self._query_or_skip(":CALCulate:MARKer1:STATe 0")
        self.assertEqual(reply, "OK")
        self.assertEqual(self._get_attribute("k__marker_1_enabled"), 0)

    def test_marker_level_matches_attribute(self):
        target = -42.5
        self._set_attribute("marker_1_level_dbm", target)
        raw = self._query_or_skip(":CALCulate:MARKer1:Y?")
        self.assertAlmostEqual(float(raw), target, places=2)


__all__ = ["TestScpiSiglentSsa3000xSutExample"]
