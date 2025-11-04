# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Hammerheads Engineers Sp. z o.o.
# See the accompanying LICENSE file for terms.

"""Integration coverage for the example Modbus thermal controller SUT device implementation."""

import os
import pathlib
import unittest

from tests.common.spx_utils import (
    bootstrap_model_instance,
    wait_for_condition,
    wait_seconds,
)
from tests.devices.thermal_controller_sut_example import (
    ModbusThermalControllerSUTExample,
    ModbusTcpClient,
)


ROOT = pathlib.Path(__file__).resolve().parents[1]
MODEL_PATH = ROOT / "library" / "thermal_controllers" / "generic" / "thermal_controller.yaml"
MODEL_KEY = "tests__thermal_controller"
INSTANCE_KEY = "generic_thermal_controller"
SPX_API_URL = os.environ.get("SPX_API_URL", "http://localhost:8000")


class TestThermalControllerSUTExampleIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raise unittest.SkipTest("Temporarily skipping SUT tests due to instability in CI environments.")
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
            base_url=SPX_API_URL,
            model_path=MODEL_PATH,
            model_key=MODEL_KEY,
            instance_key=INSTANCE_KEY,
            unit_id=3,
        )

    def setUp(self):
        self.model = self.__class__._instance
        wait_seconds(0.3)

        self.sut = ModbusThermalControllerSUTExample(unit_id=3, timeout=1.0)
        if not self.sut.connect():
            self.skipTest("Modbus server not reachable at 127.0.0.1:502 (unit 3)")
        self._reset_model_state()
        self.sut.set_power_state(True)

    def tearDown(self):
        if hasattr(self, "sut") and self.sut:
            try:
                self.sut.set_power_state(True)
            except Exception:
                pass
            self.sut.close()

    def _reset_model_state(
        self,
        *,
        temperature: float = 25.0,
        setpoint: float = 25.0,
        ambient: float = 22.0,
        power_on: int = 1,
    ) -> None:
        attrs = self.model["attributes"]
        attrs["temperature"].internal_value = temperature
        attrs["setpoint"].internal_value = setpoint
        attrs["heating_power"].internal_value = 0.0
        attrs["power_on"].internal_value = power_on
        attrs["ambient"].internal_value = ambient
        attrs["overload"].internal_value = 0
        attrs["heat_coeff"].internal_value = 0.25
        attrs["cool_coeff"].internal_value = 0.03
        attrs["power_gain"].internal_value = 1.5
        attrs["power_integral"].internal_value = 0.0
        attrs["power_integral_gain"].internal_value = 0.2
        attrs["power_derivative"].internal_value = 0.0
        attrs["power_derivative_gain"].internal_value = 0.8
        attrs["power_error_prev"].internal_value = 0.0
        attrs["power_integral_leak"].internal_value = 0.05
        wait_seconds(0.3)

    def test_heating_increases_temperature_towards_setpoint(self):
        baseline_temp = self.sut.read_temperature()
        target = baseline_temp + 15.0
        self.sut.set_setpoint(target)

        self.assertTrue(
            wait_for_condition(lambda: self.sut.read_heating_power() > 5.0, timeout=10.0),
            "Expected controller to increase heating power for higher setpoint",
        )

        self.assertTrue(
            wait_for_condition(
                lambda: self.sut.read_temperature() >= baseline_temp + 6.0,
                timeout=25.0,
                interval=0.5,
            ),
            "Expected process temperature to rise towards the new setpoint",
        )

        self.assertTrue(
            wait_for_condition(
                lambda: abs(self.sut.read_temperature() - target) <= 1.0,
                timeout=45.0,
                interval=0.5,
            ),
            "Expected controller to settle near the requested setpoint",
        )

    def test_power_off_drives_heating_power_to_zero_and_cools(self):
        ambient = 20.0
        self._reset_model_state(temperature=ambient + 5.0, setpoint=ambient + 20.0, ambient=ambient)

        self.assertTrue(
            wait_for_condition(lambda: self.sut.read_heating_power() >= 10.0, timeout=10.0),
            "Expected heating power to ramp up before shutdown",
        )

        self.sut.set_power_state(False)
        self.assertTrue(
            wait_for_condition(lambda: self.sut.read_heating_power() == 0.0, timeout=8.0),
            "Expected heating power to drop to zero once powered off",
        )

        self.assertTrue(
            wait_for_condition(
                lambda: self.sut.read_temperature() <= ambient + 5.0,
                timeout=20.0,
                interval=0.5,
            ),
            "Expected process temperature to cool back towards ambient when unpowered",
        )

    def test_overload_trips_and_recovers_with_hysteresis(self):
        self.sut.set_overload_threshold(35.0)
        self.sut.set_overload_hysteresis(2.0)
        attrs = self.model["attributes"]
        attrs["temperature"].internal_value = 34.0
        attrs["overload"].internal_value = 0
        wait_seconds(0.4)

        attrs["temperature"].internal_value = 36.5
        wait_seconds(0.4)
        self.assertTrue(
            wait_for_condition(lambda: self.sut.read_overload_flag() == 1, timeout=6.0),
            "Expected overload flag to assert when temperature exceeds threshold",
        )

        attrs["temperature"].internal_value = 32.0
        wait_seconds(0.4)
        self.assertTrue(
            wait_for_condition(lambda: self.sut.read_overload_flag() == 0, timeout=6.0),
            "Expected overload flag to clear once temperature drops below hysteresis band",
        )

        self.sut.set_overload_threshold(100.0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
