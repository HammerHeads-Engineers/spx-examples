# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Hammerheads Engineers Sp. z o.o.
# See the accompanying LICENSE file for terms.

"""Shared integration coverage for the Modbus energy meter SUT example."""

import os
import unittest

from tests.common.modbus_utils import wait_for_modbus_endpoint
from tests.common.repo import repo_root
from tests.common.spx_utils import (
    bootstrap_model_instance,
    wait_for_condition,
    wait_seconds,
)
from tests.devices.modbus_energy_meter_sut_example import (
    ModbusEnergyMeterSUTExample,
    ModbusTcpClient,
)


ROOT = repo_root()
MODEL_PATH = ROOT / "library" / "domains" / "iot" / "socomec" / "diris_a10__modbus.yaml"
MODEL_KEY = "tests__energy_meter_diris_a10"
INSTANCE_KEY = "generic_energy_meter_diris_a10"
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
            raise unittest.SkipTest("SPX_PRODUCT_KEY must be set to run integration tests.")

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

        # Ensure the Modbus adapter is attached before talking to it.
        for comm_key in ("modbus_slave", "modbus_tcp"):
            try:
                comm = self.model["communication"][comm_key]
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
            self.skipTest(f"Modbus server not reachable at 127.0.0.1:{port} (unit {unit_id})")
        self._reset_model_state()

    def tearDown(self):
        if hasattr(self, "sut") and self.sut:
            self.sut.close()

    def _reset_model_state(
        self,
        *,
        voltage_l1: float = 230.0,
        voltage_l2: float = 228.5,
        voltage_l3: float = 231.2,
        current_l1: float = 12.0,
        current_l2: float = 11.0,
        current_l3: float = 13.0,
        frequency_hz: float = 50.0,
        power_factor: float = 0.95,
        energy_import_kwh: float = 1234.0,
        energy_export_kwh: float = 56.0,
    ) -> None:
        attrs = self.model["attributes"]
        attrs["k__voltage_l1_n_v"].internal_value = voltage_l1
        attrs["k__voltage_l2_n_v"].internal_value = voltage_l2
        attrs["k__voltage_l3_n_v"].internal_value = voltage_l3
        attrs["k__current_l1_a"].internal_value = current_l1
        attrs["k__current_l2_a"].internal_value = current_l2
        attrs["k__current_l3_a"].internal_value = current_l3
        attrs["k__frequency_hz"].internal_value = frequency_hz
        attrs["k__power_factor"].internal_value = power_factor
        attrs["k__energy_import_total_kwh"].internal_value = energy_import_kwh
        attrs["k__energy_export_total_kwh"].internal_value = energy_export_kwh
        attrs["_cycle_time_s"].internal_value = 0.0
        wait_seconds(0.3)

    def test_voltage_current_frequency_scaling(self):
        self._reset_model_state(
            voltage_l1=229.4,
            current_l1=12.5,
            frequency_hz=49.8,
        )

        self.assertTrue(
            wait_for_condition(
                lambda: abs(self.sut.read_voltage_l1_n() - 229.4) <= 0.1,
                timeout=6.0,
                interval=0.2,
            ),
            "Expected L1-N voltage to match Modbus scaled value",
        )
        self.assertTrue(
            wait_for_condition(
                lambda: abs(self.sut.read_current_l1() - 12.5) <= 0.05,
                timeout=6.0,
                interval=0.2,
            ),
            "Expected L1 current to match Modbus scaled value",
        )
        self.assertTrue(
            wait_for_condition(
                lambda: abs(self.sut.read_frequency() - 49.8) <= 0.05,
                timeout=6.0,
                interval=0.2,
            ),
            "Expected frequency to match Modbus scaled value",
        )

    def test_power_and_energy_registers(self):
        self._reset_model_state(
            voltage_l1=231.0,
            voltage_l2=229.0,
            voltage_l3=230.0,
            current_l1=10.0,
            current_l2=9.5,
            current_l3=10.5,
            power_factor=0.9,
            energy_import_kwh=222.0,
            energy_export_kwh=14.0,
        )

        expected_active_kw = 1e-3 * 0.9 * (
            231.0 * 10.0 + 229.0 * 9.5 + 230.0 * 10.5
        )

        self.assertTrue(
            wait_for_condition(
                lambda: abs(self.sut.read_active_power_total_kw() - expected_active_kw) <= 0.05,
                timeout=6.0,
                interval=0.2,
            ),
            "Expected total active power to match Modbus scaled value",
        )
        self.assertTrue(
            wait_for_condition(
                lambda: abs(self.sut.read_power_factor() - 0.9) <= 0.01,
                timeout=6.0,
                interval=0.2,
            ),
            "Expected power factor to match Modbus scaled value",
        )
        self.assertTrue(
            wait_for_condition(
                lambda: self.sut.read_energy_import_kwh() == 222.0,
                timeout=6.0,
                interval=0.2,
            ),
            "Expected import energy to match Modbus scaled value",
        )
        self.assertTrue(
            wait_for_condition(
                lambda: self.sut.read_energy_export_kwh() == 14.0,
                timeout=6.0,
                interval=0.2,
            ),
            "Expected export energy to match Modbus scaled value",
        )
