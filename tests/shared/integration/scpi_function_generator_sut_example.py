# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Hammerheads Engineers Sp. z o.o.
# See the accompanying LICENSE file for terms.

"""Shared integration coverage for the example SCPI function generator SUT."""

import os
import unittest

from tests.common.ascii_utils import wait_for_ascii_port
from tests.common.spx_utils import bootstrap_model_instance, wait_seconds, wait_for_condition
from tests.common.repo import repo_root
from tests.devices.scpi_function_generator_sut_example import ScpiFunctionGeneratorSUTExample


ROOT = repo_root()
MODEL_PATH = (
    ROOT
    / "library"
    / "domains"
    / "measurement_instruments"
    / "siglent"
    / "siglent_sdg1032x__scpi.yaml"
)
MODEL_KEY = "tests__scpi_function_generator"
INSTANCE_KEY = "siglent_sdg1032x_function_generator"
SPX_BASE_URL = os.environ.get("SPX_BASE_URL", "http://localhost:8000")


class TestScpiFunctionGeneratorSUTExample(unittest.TestCase):
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
            self.skipTest("SCPI function generator instance not initialised")

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
        self.sut = ScpiFunctionGeneratorSUTExample(port=port, debug=debug)
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
        self.assertIn("SDG1032X", reply)

    def test_basic_wave_roundtrip(self):
        channel = 1
        self.sut.set_waveform(channel, "SQUARE")
        self.sut.set_frequency(channel, 2500.0)
        self.sut.set_amplitude(channel, 3.3)
        self.sut.set_offset(channel, 0.1)
        wait_seconds(0.2)

        status = self.sut.query_basic_wave(channel)
        self.assertIn("WVTP,SQUARE", status)
        self.assertIn("FRQ,2500.0", status)

        self.assertEqual(self._get_attribute("k__ch1_waveform"), "SQUARE")
        self.assertAlmostEqual(self._get_attribute("k__ch1_frequency_hz"), 2500.0, places=2)
        self.assertAlmostEqual(self._get_attribute("k__ch1_amplitude_vpp"), 3.3, places=2)
        self.assertAlmostEqual(self._get_attribute("k__ch1_offset_v"), 0.1, places=2)

    def test_output_state_roundtrip(self):
        channel = 1
        self.sut.output_on(channel)
        wait_seconds(0.2)
        status = self.sut.query_output_status(channel)
        self.assertTrue(status.startswith("C1:OUTP ON"))
        self.assertEqual(self._get_attribute("k__ch1_output_state"), "ON")

        self.sut.output_off(channel)
        wait_seconds(0.2)
        status = self.sut.query_output_status(channel)
        self.assertTrue(status.startswith("C1:OUTP OFF"))
        self.assertEqual(self._get_attribute("k__ch1_output_state"), "OFF")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
