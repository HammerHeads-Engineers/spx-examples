# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Hammerheads Engineers Sp. z o.o.
# See the accompanying LICENSE file for terms.

"""Shared integration coverage for the Keysight E36312A SCPI SUT example."""

import os
import unittest

from tests.common.ascii_utils import wait_for_ascii_port
from tests.common.repo import repo_root
from tests.common.spx_utils import bootstrap_model_instance, wait_for_condition, wait_seconds
from tests.devices.scpi_power_supply_sut_example import ScpiPowerSupplySUTExample


ROOT = repo_root()
MODEL_PATH = (
    ROOT
    / "library"
    / "domains"
    / "measurement_instruments"
    / "keysight"
    / "keysight_e36312a__scpi.yaml"
)
MODEL_KEY = "tests__scpi_keysight_e36312a"
INSTANCE_KEY = "keysight_e36312a"
SPX_BASE_URL = os.environ.get("SPX_BASE_URL", "http://localhost:8000")


class TestScpiKeysightE36312ASUTExample(unittest.TestCase):
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
            self.skipTest("SCPI power supply instance not initialised")

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
        self.sut = ScpiPowerSupplySUTExample(port=port, debug=debug)
        try:
            connected = wait_for_condition(lambda: self.sut.connect(), timeout=5.0, interval=0.2)
        except OSError as exc:
            self.skipTest(f"Unable to connect to SCPI server on port {port}: {exc}")
        if not connected:
            self.skipTest(f"ASCII/SCPI server not reachable at 127.0.0.1:{port}")
        wait_seconds(0.2)

        for channel in (1, 2, 3):
            try:
                self.sut.output_off(channel)
            except Exception:
                pass
        wait_seconds(0.1)

    def tearDown(self):
        if hasattr(self, "sut") and self.sut:
            self.sut.close()

    def _query_or_skip(self, command: str) -> str:
        reply = self.sut.query(command)
        if reply == "":
            self.skipTest(f"No response from SCPI server for command '{command}'.")
        return reply

    def test_idn_returns_keysight_signature(self):
        reply = self._query_or_skip("*IDN?")
        self.assertIn("KEYSIGHT", reply.upper())

    def test_output_select_round_trip(self):
        reply = self._query_or_skip(":INSTrument:NSELect 2")
        self.assertEqual(reply, "OK")
        wait_seconds(0.1)
        selected = int(float(self._query_or_skip(":INSTrument:NSELect?")))
        self.assertEqual(selected, 2)

    def test_channel_1_voltage_current_round_trip(self):
        self.sut.set_voltage(1, 4.2)
        self.sut.set_current(1, 0.35)
        self.sut.output_on(1)
        wait_seconds(0.2)
        voltage = self.sut.measure_voltage(1)
        current = self.sut.measure_current(1)

        self.assertAlmostEqual(voltage, 4.2, places=2)
        self.assertAlmostEqual(current, 0.35, places=2)

    def test_channel_2_output_state(self):
        self.sut.output_on(2)
        wait_seconds(0.1)
        state = self.sut.output_state(2)
        self.assertEqual(state, 1)
        self.sut.output_off(2)
        wait_seconds(0.1)
        state = self.sut.output_state(2)
        self.assertEqual(state, 0)


__all__ = ["TestScpiKeysightE36312ASUTExample"]
