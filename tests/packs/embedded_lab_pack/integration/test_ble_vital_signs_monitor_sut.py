# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Hammerheads Engineers Sp. z o.o.
# See the accompanying LICENSE file for terms.

"""Integration coverage for the BLE vital signs monitor SUT helper."""

from __future__ import annotations

import os
import unittest

from tests.common.spx_utils import require_existing_instance, wait_for_condition, wait_seconds
from tests.devices.ble_vital_signs_monitor_sut import BleVitalSignsMonitorSUT


class TestBleVitalSignsMonitorSUTIntegration(unittest.TestCase):
    """Validates the BLE facade against a running SPX vital signs instance."""

    SPX_API_URL = os.environ.get("SPX_API_URL", "http://localhost:8000")
    INSTANCE_KEY = "spx_health_monitor_ble"
    MODEL_ID = "Embedded.HealthMonitor.BleGatt"

    @classmethod
    def setUpClass(cls):
        try:
            import spx_python  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dependency guard
            raise unittest.SkipTest(f"spx_python not available: {exc}") from exc

        product_key = os.environ.get("SPX_PRODUCT_KEY")
        if not product_key:
            raise unittest.SkipTest("SPX_PRODUCT_KEY must be set to run BLE SUT tests.")

        cls._spx_client = spx_python.init(address=cls.SPX_API_URL, product_key=product_key)
        cls._instance = require_existing_instance(
            cls._spx_client,
            cls.INSTANCE_KEY,
            expected_model_id=cls.MODEL_ID,
            ensure_running=False,
        )

        try:
            cls._instance.stop()
        except Exception:
            pass
        try:
            cls._instance.reset()
        except Exception:
            pass
        try:
            cls._instance.start()
        except Exception:
            pass

    def setUp(self) -> None:
        self._instance = self.__class__._instance
        self._attributes = self._instance["attributes"]

        self._ensure_scenario_stopped("deep_sleep")
        self._ensure_scenario_stopped("focused_work")
        self._ensure_scenario_stopped("brisk_walk")
        self._ensure_scenario_stopped("interval_training")
        self._ensure_scenario_stopped("acute_stress_event")
        self._ensure_scenario_stopped("cooldown_recovery")
        wait_seconds(0.1)

        self.sut = BleVitalSignsMonitorSUT(
            spx_client=self.__class__._spx_client,
            spx_instance=self._instance,
            spx_instance_key=self.INSTANCE_KEY,
        )

    def test_read_activity_intensity_live(self):
        target_value = 0.42
        attr = self._attributes["activityIntensity"]
        attr.internal_value = target_value

        value = self.sut.read_activity_intensity()
        self.assertIsInstance(value, float)
        self.assertAlmostEqual(target_value, value, places=6)

    def test_read_body_temperature_matches_attribute(self):
        expected = 37.25
        self._freeze_attribute("bodyTemperatureC", "temperatureSmoothing", expected)

        value = self.sut.read_body_temperature()
        self.assertAlmostEqual(expected, value, places=3)

    def test_read_heart_rate_matches_attribute(self):
        expected = 132.0
        self._freeze_attribute("heartRateBpm", "heartRateSmoothing", expected)

        value = self.sut.read_heart_rate()
        self.assertAlmostEqual(expected, value, places=1)

    def test_read_blood_oxygen_matches_attribute(self):
        expected = 96.4
        self._freeze_attribute("bloodOxygenPercent", "spo2Smoothing", expected)

        value = self.sut.read_blood_oxygen()
        self.assertAlmostEqual(expected, value, places=2)

    # def test_brisk_walk_scenario_adjusts_activity_intensity(self):
    #     scenarios = self._instance["scenarios"]
    #     scenario = scenarios["brisk_walk"]
    #     if scenario is None:
    #         self.skipTest("Scenario 'brisk_walk' not available on instance.")

    #     start = getattr(scenario, "start", None)
    #     if not callable(start):
    #         self.skipTest("Scenario 'brisk_walk' does not expose start().")

    #     stop = getattr(scenario, "stop", None)
    #     if callable(stop):
    #         self.addCleanup(lambda: self._safe_call(stop))

    #     baseline = 0.1
    #     target = 0.6
    #     attr = self._attributes["activityIntensity"]
    #     attr.internal_value = baseline
    #     self.addCleanup(lambda: self._reset_activity_intensity())

    #     def _read_activity_intensity() -> float:
    #         try:
    #             value = float(attr.internal_value)
    #         except Exception:
    #             value = float("nan")
    #         try:
    #             raw = attr.get()
    #         except Exception:
    #             raw = None
    #         if isinstance(raw, dict):
    #             raw = raw.get("value", raw.get("state"))
    #         if raw is not None:
    #             try:
    #                 value = float(raw)
    #             except Exception:
    #                 pass
    #         return value

    #     start()
    #     converged = wait_for_condition(
    #         lambda: abs(_read_activity_intensity() - target) <= 0.05,
    #         timeout=6.0,
    #         interval=0.2,
    #     )
    #     self.assertTrue(converged, "Scenario did not drive activityIntensity to expected target.")

    #     value = self.sut.read_activity_intensity()
    #     self.assertAlmostEqual(target, value, delta=0.05)

    def _set_attribute(self, name: str, value) -> None:
        attr = self._attributes[name]
        if attr is not None:
            attr.internal_value = value

    def _freeze_attribute(self, value_attr: str, smoothing_attr: str, target_value) -> None:
        original_smoothing = self._get_internal_value(smoothing_attr)
        if original_smoothing is None:
            raise self.failureException(f"Smoothing attribute '{smoothing_attr}' not available.")

        self._set_attribute(smoothing_attr, 0.0)
        self.addCleanup(lambda: self._set_attribute(smoothing_attr, original_smoothing))
        self._set_attribute(value_attr, target_value)

    def _get_internal_value(self, name: str):
        attr = self._attributes[name]
        if attr is None:
            return None
        return getattr(attr, "internal_value", None)

    def _reset_activity_intensity(self, value: float = 0.15) -> None:
        try:
            attr = self._attributes["activityIntensity"]
        except Exception:
            return
        attr.internal_value = value

    def _ensure_scenario_stopped(self, name: str) -> None:
        try:
            scenario = self._instance["scenarios"][name]
        except Exception:
            return
        stop = getattr(scenario, "stop", None)
        if callable(stop):
            try:
                stop()
            except Exception:
                return
            wait_seconds(0.1)

    @staticmethod
    def _safe_call(func):
        try:
            func()
        except Exception:
            pass


# Backward-compatibility alias for tooling referencing the previous class name.
TestBleVitalSignsMonitorSUT = TestBleVitalSignsMonitorSUTIntegration


if __name__ == "__main__":  # pragma: no cover - manual execution helper
    unittest.main()
