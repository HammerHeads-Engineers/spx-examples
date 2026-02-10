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
    / "tektronix"
    / "tektronix_mdo3000__scpi.yaml"
)
MODEL_KEY = "tests__scpi_tektronix_mdo3000"
INSTANCE_KEY = "tektronix_mdo3000_oscilloscope"
SPX_BASE_URL = os.environ.get("SPX_BASE_URL", "http://localhost:8000")


class TestScpiTektronixMdo3000SutExample(unittest.TestCase):
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
            self.skipTest("Tektronix MDO3000 instance not initialised")

        self._ensure_scenario_stopped("calibration_tone")
        self._ensure_scenario_stopped("transient_spike")
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

    def _write_and_drain(self, command: str) -> None:
        self.sut.write(command)
        self.sut.drain()

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------
    def test_idn_matches_attribute(self):
        target = "TEKTRONIX,MDO3000,0000000,1.0"
        self._set_attribute("idn", target)
        reply = self._query_or_skip("*IDN?")
        self.assertEqual(reply, target)

    def test_measurement_value_matches_type(self):
        self._set_attribute("channel1_vpp_v", 2.5)
        self._set_attribute("channel1_vrms_v", 0.88)
        self._set_attribute("channel1_vavg_v", 0.12)
        self._set_attribute("channel1_freq_hz", 1234.0)
        self._set_attribute("channel1_period_s", 0.00075)

        self._write_and_drain(":MEASUrement:IMMed:TYPe VPP")
        wait_seconds(0.1)
        vpp = float(self._query_or_skip(":MEASUrement:IMMed:VALue?"))
        self.assertAlmostEqual(vpp, 2.5, places=2)

        self._write_and_drain(":MEASUrement:IMMed:TYPe VRMS")
        wait_seconds(0.1)
        vrms = float(self._query_or_skip(":MEASUrement:IMMed:VALue?"))
        self.assertAlmostEqual(vrms, 0.88, places=2)

        self._write_and_drain(":MEASUrement:IMMed:TYPe MEAN")
        wait_seconds(0.1)
        vavg = float(self._query_or_skip(":MEASUrement:IMMed:VALue?"))
        self.assertAlmostEqual(vavg, 0.12, places=2)

        self._write_and_drain(":MEASUrement:IMMed:TYPe FREQ")
        wait_seconds(0.1)
        freq = float(self._query_or_skip(":MEASUrement:IMMed:VALue?"))
        self.assertAlmostEqual(freq, 1234.0, places=1)

        self._write_and_drain(":MEASUrement:IMMed:TYPe PER")
        wait_seconds(0.1)
        period = float(self._query_or_skip(":MEASUrement:IMMed:VALue?"))
        self.assertAlmostEqual(period, 0.00075, places=5)

    def test_channel_scale_round_trip(self):
        self._write_and_drain(":CHANnel1:SCAle 0.2")
        wait_seconds(0.1)
        scale = float(self._query_or_skip(":CHANnel1:SCAle?"))
        self.assertAlmostEqual(scale, 0.2, places=3)
        self.assertAlmostEqual(self._get_attribute("k__channel_1_scale_v"), 0.2, places=3)

    def test_timebase_scale_round_trip(self):
        self._write_and_drain(":HORizontal:MAIn:SCAle 0.0005")
        wait_seconds(0.1)
        scale = float(self._query_or_skip(":HORizontal:MAIn:SCAle?"))
        self.assertAlmostEqual(scale, 0.0005, places=6)
        self.assertAlmostEqual(self._get_attribute("k__timebase_scale_s"), 0.0005, places=6)

    def test_trigger_level_round_trip(self):
        self._write_and_drain(":TRIGger:A:LEVel 0.05")
        wait_seconds(0.1)
        level = float(self._query_or_skip(":TRIGger:A:LEVel?"))
        self.assertAlmostEqual(level, 0.05, places=3)
        self.assertAlmostEqual(self._get_attribute("k__trigger_level_v"), 0.05, places=3)

    def test_measurement_source_round_trip(self):
        reply = self._query_or_skip(":MEASUrement:IMMed:SOUrce CH1")
        self.assertEqual(reply, "OK")
        wait_seconds(0.1)
        self.assertEqual(self._get_attribute("k__measurement_source"), "CH1")
        source = self._query_or_skip(":MEASUrement:IMMed:SOUrce?")
        self.assertEqual(source, "CH1")

    def test_system_error_reports_no_error(self):
        reply = self._query_or_skip(":SYSTem:ERRor?")
        self.assertIn("No error", reply)

    def test_calibration_tone_scenario_sets_targets(self):
        scenarios = self.instance["scenarios"]
        scenario = scenarios["calibration_tone"]
        self._set_attribute("channel1_vpp_v", 0.0)
        self._set_attribute("channel1_freq_hz", 0.0)
        start = getattr(scenario, "start", None)
        if callable(start):
            start()
        wait_seconds(0.3)

        self._write_and_drain(":MEASUrement:IMMed:TYPe VPP")
        wait_seconds(0.1)
        vpp = float(self._query_or_skip(":MEASUrement:IMMed:VALue?"))
        self.assertAlmostEqual(vpp, 2.0, places=2)

        self._write_and_drain(":MEASUrement:IMMed:TYPe FREQ")
        wait_seconds(0.1)
        freq = float(self._query_or_skip(":MEASUrement:IMMed:VALue?"))
        self.assertAlmostEqual(freq, 1000.0, places=1)


__all__ = ["TestScpiTektronixMdo3000SutExample"]
