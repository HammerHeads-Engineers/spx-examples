# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Hammerheads Engineers Sp. z o.o.
# See the accompanying LICENSE file for terms.

"""Integration coverage for the Modbus EM24 energy meter SUT implementation."""

import os
import unittest

from tests.common.modbus_utils import wait_for_modbus_endpoint
from tests.common.spx_utils import (
    bootstrap_model_instance,
    wait_for_condition,
    wait_seconds,
)
from tests.common.repo import repo_root
from tests.devices.modbus_em24_sut_example import (
    ModbusEm24SUTExample,
    ModbusTcpClient,
)


ROOT = repo_root()
MODEL_PATH = (
    ROOT
    / "library"
    / "domains"
    / "iot"
    / "carlo_gavazzi"
    / "carlo_gavazzi_em24__modbus.yaml"
)
MODEL_KEY = "tests__em24_energy_meter"
INSTANCE_KEY = "carlo_gavazzi_em24"
SPX_BASE_URL = os.environ.get("SPX_BASE_URL", "http://localhost:8000")


class TestModbusEm24SUTExampleIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if ModbusTcpClient is None:  # pragma: no cover - dependency missing
            raise unittest.SkipTest(
                "pymodbus is not available. Install pymodbus to run Modbus integration tests."
            )

        try:
            import spx_python  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise unittest.SkipTest(f"spx_python not available: {exc}") from exc

        product_key = os.environ.get("SPX_PRODUCT_KEY")
        if not product_key:
            raise unittest.SkipTest(
                "SPX_PRODUCT_KEY must be set to run integration tests."
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
        self.model = self.__class__._instance
        wait_seconds(0.2)

        for scenario_name in (
            "balanced_load",
            "inductive_load",
            "pv_export",
        ):
            try:
                scenario = self.model["scenarios"][scenario_name]
            except Exception:
                continue
            stop = getattr(scenario, "stop", None)
            if callable(stop):
                try:
                    stop()
                except Exception:
                    pass
        wait_seconds(0.1)

        try:
            comm = self.model["communication"]["modbus_slave"]
            attach = getattr(comm, "attach", None)
            if callable(attach):
                attach()
        except Exception:
            pass

        try:
            port, unit_id = wait_for_modbus_endpoint(
                self.model,
                comm_keys=("modbus_slave", "modbus_tcp"),
                timeout=10.0,
                interval=0.2,
            )
        except TimeoutError as exc:
            self.skipTest(str(exc))

        self.sut = ModbusEm24SUTExample(
            host="127.0.0.1",
            port=port,
            unit_id=unit_id,
            timeout=1.0,
        )
        if not wait_for_condition(lambda: self.sut.connect(), timeout=5.0, interval=0.2):
            self.skipTest(
                f"Modbus server not reachable at 127.0.0.1:{port} (unit {unit_id})"
            )
        wait_seconds(0.2)

    def tearDown(self):
        if hasattr(self, "sut") and self.sut:
            self.sut.close()

    def _set_attribute(self, name: str, value) -> None:
        attrs = self.model["attributes"]
        attrs[name].internal_value = value
        wait_seconds(0.1)

    def test_voltage_l1_matches_attribute(self):
        target_voltage = 231.5
        self._set_attribute("k__voltage_l1_n_v", target_voltage)
        reading = self.sut.read_voltage_l1_n_v()
        self.assertAlmostEqual(reading, target_voltage, places=1)

    def test_current_l1_matches_attribute(self):
        target_current = 7.125
        self._set_attribute("k__current_l1_a", target_current)
        reading = self.sut.read_current_l1_a()
        self.assertAlmostEqual(reading, target_current, places=3)

    def test_frequency_matches_attribute(self):
        target_frequency = 49.7
        self._set_attribute("k__frequency_hz", target_frequency)
        reading = self.sut.read_frequency_hz()
        self.assertAlmostEqual(reading, target_frequency, places=1)

    def test_active_power_total_from_phase_inputs(self):
        for name in (
            "k__voltage_l1_n_v",
            "k__voltage_l2_n_v",
            "k__voltage_l3_n_v",
        ):
            self._set_attribute(name, 230.0)
        for name in (
            "k__current_l1_a",
            "k__current_l2_a",
            "k__current_l3_a",
        ):
            self._set_attribute(name, 10.0)
        for name in (
            "k__power_factor_l1",
            "k__power_factor_l2",
            "k__power_factor_l3",
        ):
            self._set_attribute(name, 0.9)

        expected_total = 3 * 230.0 * 10.0 * 0.9
        reading = self.sut.read_active_power_total_w()
        self.assertAlmostEqual(reading, expected_total, delta=5.0)

    def test_energy_import_total_matches_attribute(self):
        for name in (
            "k__current_l1_a",
            "k__current_l2_a",
            "k__current_l3_a",
        ):
            self._set_attribute(name, 0.0)
        self._set_attribute("energy_import_total_kwh", 12.3)
        reading = self.sut.read_energy_import_total_kwh()
        self.assertAlmostEqual(reading, 12.3, places=1)
