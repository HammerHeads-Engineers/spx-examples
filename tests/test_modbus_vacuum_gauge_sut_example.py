"""Integration coverage for the example Modbus vacuum gauge SUT device implementation."""

import os
import pathlib
import unittest

from tests.common.spx_utils import (
    bootstrap_model_instance,
    wait_for_condition,
    wait_seconds,
)
from tests.devices.modbus_vacuum_gauge_sut_example import (
    ModbusVacuumGaugeSUTExample,
    ModbusTcpClient,
)


ROOT = pathlib.Path(__file__).resolve().parents[1]
MODEL_PATH = ROOT / "library" / "vacuum_systems" / "generic" / "vacuum_gauge.yaml"
MODEL_KEY = "tests__vacuum_gauge"
INSTANCE_KEY = "generic_vacuum_gauge"
SPX_API_URL = os.environ.get("SPX_API_URL", "http://localhost:8000")


class TestModbusVacuumGaugeSUTExampleIntegration(unittest.TestCase):
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
            base_url=SPX_API_URL,
            model_path=MODEL_PATH,
            model_key=MODEL_KEY,
            instance_key=INSTANCE_KEY,
            unit_id=1,
        )

    def setUp(self):
        self.model = self.__class__._instance
        wait_seconds(0.5)

        self.sut = ModbusVacuumGaugeSUTExample(unit_id=1, timeout=1.0)
        if not self.sut.connect():
            self.skipTest(
                "Modbus server not reachable at 127.0.0.1:502 (unit 1)"
            )
        wait_seconds(0.2)

    def tearDown(self):
        if hasattr(self, "sut") and self.sut:
            try:
                self.sut.set_coil("leak_event", 0)
                self.sut.set_coil("discharge_event", 0)
            except Exception:
                pass
            self.sut.close()
        # self.model.reset()

    def _prime_pressures(self, rough: float, high: float) -> None:
        attrs = self.model["attributes"]
        attrs["rough_pressure"].internal_value = rough
        attrs["high_pressure"].internal_value = high
        wait_seconds(0.2)

    def _read_pressures(self):
        return self.sut.read_rough_pressure(), self.sut.read_high_pressure()

    def test_pumpdown(self):
        self._prime_pressures(rough=0.5, high=0.5)

        rough_samples = []
        high_samples = []
        for _ in range(12):
            wait_seconds(0.4)
            rough, high = self._read_pressures()
            rough_samples.append(rough)
            high_samples.append(high)

        self.assertTrue(rough_samples, "Expected to collect rough pressure samples")
        self.assertTrue(high_samples, "Expected to collect high pressure samples")

        initial_rough = rough_samples[0]
        final_rough = rough_samples[-1]
        initial_high = high_samples[0]
        final_high = high_samples[-1]

        self.assertLess(
            final_rough,
            initial_rough * 0.9,
            f"Expected rough pressure to decrease, observed {initial_rough:.3e} -> {final_rough:.3e}",
        )
        self.assertLess(
            final_high,
            initial_high * 0.9,
            f"Expected high-vacuum pressure to decrease, observed {initial_high:.3e} -> {final_high:.3e}",
        )

    def test_discharge_spike_scenario(self):
        discharge_pressure = float(
            self.model["attributes"]["discharge_pressure"].internal_value
        )
        self._prime_pressures(rough=0.1, high=0.05)
        wait_for_condition(lambda: self._read_pressures()[1] < 5e-3, timeout=10.0)
        baseline_rough, baseline_high = self._read_pressures()

        # scenario = self.model["scenarios"]["discharge_spike"]
        # scenario.start()

        self.model["attributes"]["discharge_event"].internal_value = 1
        wait_seconds(0.2)

        self.assertTrue(
            wait_for_condition(
                lambda: self._read_pressures()[1] >= discharge_pressure * 0.7,
                timeout=6.0,
            ),
            "Expected discharge spike to raise the high-vacuum pressure",
        )
        spike_rough, spike_high = self._read_pressures()
        self.assertGreater(spike_high, baseline_high)
        self.assertGreater(spike_rough, baseline_rough)

        self.assertTrue(
            wait_for_condition(
                lambda: self._read_pressures()[1] < spike_high * 0.7,
                timeout=8.0,
            ),
            "Expected pressure to recover after discharge event",
        )

    def test_leak_event_causes_pressure_rise_and_recovery(self):
        self._prime_pressures(rough=0.05, high=0.05)
        wait_for_condition(lambda: self._read_pressures()[1] < 5e-3, timeout=10.0)

        baseline_rough, baseline_high = self._read_pressures()
        upset_target = float(self.model["attributes"]["upset_target"].internal_value)

        self.sut.set_coil("leak_event", 1)
        self.assertTrue(
            wait_for_condition(
                lambda: self._read_pressures()[1] >= upset_target * 0.7,
                timeout=6.0,
            ),
            "Expected leak event to elevate high-vacuum pressure",
        )
        leak_rough, leak_high = self._read_pressures()
        self.assertGreater(leak_high, baseline_high)
        self.assertGreater(leak_rough, baseline_rough)

        self.sut.set_coil("leak_event", 0)
        self.assertTrue(
            wait_for_condition(
                lambda: self._read_pressures()[1] < leak_high * 0.6,
                timeout=10.0,
            ),
            "Expected pressure to drop after leak event clears",
        )

    def test_relay_outputs_follow_setpoints(self):
        self.sut.set_float("relay_setpoint_1", 5.0e-4)
        self.sut.set_float("relay_setpoint_2", 2.0e-4)
        # Keep remaining relays inactive by using very small thresholds.
        self.sut.set_float("relay_setpoint_3", 1.0e-9)
        self.sut.set_float("relay_setpoint_4", 1.0e-9)
        self.sut.set_float("relay_setpoint_5", 1.0e-9)
        self.sut.set_float("pumpdown_target", 1.0e-5)

        self._prime_pressures(rough=0.05, high=0.05)

        self.assertTrue(
            wait_for_condition(
                lambda: self._read_pressures()[1] <= 5.0e-4,
                timeout=15.0,
            ),
            "Expected high-vacuum pressure to fall below first relay setpoint",
        )
        self.assertEqual(self.sut.read_flag("relay_output_1"), 1)
        self.assertEqual(self.sut.read_flag("relay_output_2"), 0)

        self.assertTrue(
            wait_for_condition(
                lambda: self._read_pressures()[1] <= 2.0e-4,
                timeout=15.0,
            ),
            "Expected high-vacuum pressure to fall below second relay setpoint",
        )
        self.assertEqual(self.sut.read_flag("relay_output_2"), 1)

        self.sut.set_coil("leak_event", 1)
        self.assertTrue(
            wait_for_condition(
                lambda: self._read_pressures()[1] >= 0.01,
                timeout=8.0,
            ),
            "Expected leak event to raise pressure above relay thresholds",
        )
        wait_seconds(0.3)
        self.assertEqual(self.sut.read_flag("relay_output_1"), 0)
        self.assertEqual(self.sut.read_flag("relay_output_2"), 0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
