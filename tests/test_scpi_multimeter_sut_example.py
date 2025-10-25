# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Hammerheads Engineers Sp. z o.o.
# See the accompanying LICENSE file for terms.

"""Integration coverage for the example SCPI multimeter SUT implementation."""

import os
import pathlib
import unittest

from tests.common.spx_utils import bootstrap_model_instance, wait_seconds
from tests.devices.scpi_multimeter_sut_example import ScpiMultimeterSUTExample


ROOT = pathlib.Path(__file__).resolve().parents[1]
MODEL_PATH = ROOT / "library" / "measurement_instruments" / "generic" / "scpi_multimeter.yaml"
MODEL_KEY = "tests__scpi_multimeter"
INSTANCE_KEY = "generic_scpi_multimeter"
SPX_API_URL = os.environ.get("SPX_API_URL", "http://localhost:8000")


class TestScpiMultimeterSUTExample(unittest.TestCase):
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
            base_url=SPX_API_URL,
            model_path=MODEL_PATH,
            model_key=MODEL_KEY,
            instance_key=INSTANCE_KEY,
        )

    def setUp(self):
        self.instance = getattr(self.__class__, "_instance", None)
        if self.instance is None:  # pragma: no cover - defensive
            self.skipTest("SCPI multimeter instance not initialised")

        debug = bool(int(os.environ.get("SCPI_TEST_DEBUG", "1")))
        self.sut = ScpiMultimeterSUTExample(debug=debug)
        try:
            if not self.sut.connect():
                self.skipTest("ASCII/SCPI server not reachable at 127.0.0.1:5025")
        except OSError as exc:
            self.skipTest(f"Unable to connect to SCPI server: {exc}")
        wait_seconds(0.2)

    def tearDown(self):
        if hasattr(self, "sut") and self.sut:
            self.sut.close()

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------
    def _set_attribute(self, name: str, value) -> None:
        attrs = self.instance["attributes"]
        attrs[name].internal_value = value
        wait_seconds(0.1)

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------
    def _query_or_skip(self, command: str) -> str:
        reply = self.sut.query(command)
        if reply == "":
            self.skipTest(
                f"No response from SCPI server for command '{command}'."
            )
        return reply

    def test_measure_voltage_matches_attribute(self):
        target_voltage = 7.25
        self._set_attribute("voltage", target_voltage)
        raw = self._query_or_skip("MEAS:VOLT?")
        try:
            voltage = float(raw)
        except ValueError:
            self.fail(f"Expected numeric voltage, got '{raw}'")
        self.assertAlmostEqual(voltage, target_voltage, places=2)

    def test_unknown_command_returns_error(self):
        reply = self._query_or_skip("FOO")
        self.assertTrue(reply.startswith("-113"), f"Unexpected reply: {reply}")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
