# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Hammerheads Engineers Sp. z o.o.
# See the accompanying LICENSE file for terms.

"""Integration coverage for the Socomec DIRIS A-40 Modbus SUT device implementation."""

import os
import unittest

from tests.common.modbus_utils import wait_for_modbus_endpoint
from tests.common.spx_utils import bootstrap_model_instance, wait_for_condition, wait_seconds
from tests.common.repo import repo_root
from tests.devices.modbus_energy_meter_sut_example import (
    ModbusEnergyMeterSUTExample,
    ModbusTcpClient,
)


ROOT = repo_root()
MODEL_PATH = (
    ROOT
    / "library"
    / "domains"
    / "iot"
    / "socomec"
    / "diris_a40__modbus.yaml"
)
MODEL_KEY = "tests__diris_a40"
INSTANCE_KEY = "socomec_diris_a40"
SPX_BASE_URL = os.environ.get("SPX_BASE_URL", "http://localhost:8000")


class TestModbusEnergyMeterSUTExampleIntegration(unittest.TestCase):
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
            "peak_demand",
            "voltage_sag",
            "low_power_factor",
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

        for comm_name in ("modbus_slave", "modbus_tcp"):
            try:
                comm = self.model["communication"][comm_name]
            except Exception:
                continue
            attach = getattr(comm, "attach", None)
            if callable(attach):
                try:
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

        self._modbus_port = port
        self._modbus_unit_id = unit_id
        self.sut = ModbusEnergyMeterSUTExample(
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

    def _prime_measurements(
        self,
        voltage_l1_n: float,
        voltage_l2_n: float,
        voltage_l3_n: float,
        voltage_l1_l2: float,
        voltage_l2_l3: float,
        voltage_l3_l1: float,
        current_l1: float,
        current_l2: float,
        current_l3: float,
        frequency: float,
        power_factor: float,
    ) -> None:
        attrs = self.model["attributes"]
        attrs["k__voltage_l1_n_v"].internal_value = voltage_l1_n
        attrs["k__voltage_l2_n_v"].internal_value = voltage_l2_n
        attrs["k__voltage_l3_n_v"].internal_value = voltage_l3_n
        attrs["voltage_l1_l2_v"].internal_value = voltage_l1_l2
        attrs["voltage_l2_l3_v"].internal_value = voltage_l2_l3
        attrs["voltage_l3_l1_v"].internal_value = voltage_l3_l1
        attrs["k__current_l1_a"].internal_value = current_l1
        attrs["k__current_l2_a"].internal_value = current_l2
        attrs["k__current_l3_a"].internal_value = current_l3
        attrs["k__frequency_hz"].internal_value = frequency
        attrs["k__power_factor"].internal_value = power_factor
        wait_seconds(0.4)

    def test_instantaneous_measurements(self):
        self._prime_measurements(
            voltage_l1_n=231.0,
            voltage_l2_n=229.5,
            voltage_l3_n=230.0,
            voltage_l1_l2=412.0,
            voltage_l2_l3=408.0,
            voltage_l3_l1=410.0,
            current_l1=21.0,
            current_l2=19.5,
            current_l3=20.5,
            frequency=49.9,
            power_factor=0.97,
        )

        self.assertAlmostEqual(self.sut.read_voltage_l1_n(), 231.0, delta=0.5)
        self.assertAlmostEqual(self.sut.read_voltage_l2_n(), 229.5, delta=0.5)
        self.assertAlmostEqual(self.sut.read_voltage_l3_n(), 230.0, delta=0.5)
        self.assertAlmostEqual(self.sut.read_voltage_l1_l2(), 412.0, delta=0.5)
        self.assertAlmostEqual(self.sut.read_voltage_l2_l3(), 408.0, delta=0.5)
        self.assertAlmostEqual(self.sut.read_voltage_l3_l1(), 410.0, delta=0.5)
        self.assertAlmostEqual(self.sut.read_current_l1(), 21.0, delta=0.1)
        self.assertAlmostEqual(self.sut.read_current_l2(), 19.5, delta=0.1)
        self.assertAlmostEqual(self.sut.read_current_l3(), 20.5, delta=0.1)
        self.assertAlmostEqual(self.sut.read_frequency(), 49.9, delta=0.05)

        power = self.sut.read_active_power_l1()
        self.assertGreater(power, 0.0, "Expected positive active power on L1")

    def test_energy_accumulates(self):
        initial_energy = self.sut.read_energy_import_total()
        wait_seconds(1.5)
        updated_energy = self.sut.read_energy_import_total()
        self.assertGreaterEqual(
            updated_energy,
            initial_energy,
            "Expected total imported energy to be non-decreasing",
        )
