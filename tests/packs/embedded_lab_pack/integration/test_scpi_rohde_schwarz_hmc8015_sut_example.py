# SPDX-License-Identifier: MIT

import os
import unittest

from tests.common.ascii_utils import wait_for_ascii_port
from tests.common.spx_utils import bootstrap_model_instance, wait_seconds, wait_for_condition
from tests.common.repo import repo_root
from tests.devices.scpi_rohde_schwarz_hmc8015_sut_example import (
    ScpiRohdeSchwarzHmc8015SUTExample,
)


ROOT = repo_root()
MODEL_PATH = (
    ROOT
    / "library"
    / "domains"
    / "measurement_instruments"
    / "rohde_schwarz"
    / "rohde_schwarz_hmc8015__scpi.yaml"
)
MODEL_KEY = "tests__scpi_hmc8015"
INSTANCE_KEY = "rohde_schwarz_hmc8015_power_analyzer"
SPX_BASE_URL = os.environ.get("SPX_BASE_URL", "http://localhost:8000")


class TestScpiRohdeSchwarzHmc8015SutExample(unittest.TestCase):
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
            self.skipTest("HMC8015 instance not initialised")

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
        self.sut = ScpiRohdeSchwarzHmc8015SUTExample(port=port, debug=debug)
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
        self.assertIn("Rohde", reply)
        self.assertIn("HMC8015", reply)

    def test_measurement_functions_roundtrip(self):
        self.sut.set_measurement_functions("URMS,IRMS,P")
        self.sut.drain()
        wait_seconds(0.2)

        reply = self.sut.measurement_functions()
        self.assertEqual(reply, "URMS,IRMS,P")
        self.assertEqual(self._get_attribute("k__measurement_functions"), "URMS,IRMS,P")

    def test_measurement_data_matches_attributes(self):
        self.sut.set_measurement_functions("URMS,IRMS,P")
        self.sut.drain()
        wait_seconds(0.2)

        values = self.sut.measurement_data()
        self.assertEqual(len(values), 3)
        self.assertAlmostEqual(values[0], self._get_attribute("voltage_rms_v"), places=2)
        self.assertAlmostEqual(values[1], self._get_attribute("current_rms_a"), places=2)
        self.assertAlmostEqual(values[2], self._get_attribute("active_power_w"), places=2)

    def test_system_error_is_clear(self):
        reply = self.sut.system_error()
        self.assertTrue(reply.startswith("0,"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
