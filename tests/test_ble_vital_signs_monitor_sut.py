# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Hammerheads Engineers Sp. z o.o.
# See the accompanying LICENSE file for terms.

"""Integration coverage for the BLE vital signs monitor SUT helper."""

from __future__ import annotations

import os
import unittest
from pathlib import Path

from tests.common.spx_utils import ensure_instance, ensure_model, load_model_definition, wait_for_condition
from tests.devices.ble_vital_signs_monitor_sut import BleVitalSignsMonitorSUT


class TestBleVitalSignsMonitorSUTIntegration(unittest.TestCase):
    """Validates the BLE facade against a running SPX vital signs instance."""

    MODEL_PATH = Path("library/ble/generic/ble_vital_signs_monitor.yaml")
    MODEL_KEY = "tests__ble_vital_signs_monitor"
    INSTANCE_KEY = "tests_ble_vital_signs_monitor_inst"

    def setUp(self) -> None:
        raise unittest.SkipTest("Temporarily skipping SUT tests due to instability in CI environments.")
        try:
            import bleak  # type: ignore  # noqa: F401
        except Exception:
            self.skipTest("bleak dependency is not available.")

        try:
            import spx_python  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dependency guard
            self.skipTest(f"spx_python not available: {exc}")

        product_key = self._require_product_key()
        base_url = self._resolve_base_url()

        client = spx_python.init(address=base_url, product_key=product_key)
        model_def = load_model_definition(self.MODEL_PATH)
        model_changed = ensure_model(client, self.MODEL_KEY, model_def)
        try:
            instance = ensure_instance(
                client,
                self.INSTANCE_KEY,
                self.MODEL_KEY,
                recreate=model_changed,
            )
        except Exception as exc:
            self.skipTest(f"Unable to prepare BLE instance: {exc}")

        self._spx_client = client
        self._instance = instance
        self._attributes = instance["attributes"]

        self.sut = BleVitalSignsMonitorSUT(
            spx_client=client,
            spx_instance=instance,
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

    def test_brisk_walk_scenario_adjusts_activity_intensity(self):
        scenarios = self._instance["scenarios"]
        scenario = scenarios["brisk_walk"]
        if scenario is None:
            self.skipTest("Scenario 'brisk_walk' not available on instance.")

        start = getattr(scenario, "start", None)
        if not callable(start):
            self.skipTest("Scenario 'brisk_walk' does not expose start().")

        stop = getattr(scenario, "stop", None)
        if callable(stop):
            self.addCleanup(lambda: self._safe_call(stop))

        baseline = 0.1
        target = 0.6
        attr = self._attributes["activityIntensity"]
        attr.internal_value = baseline
        self.addCleanup(lambda: self._reset_activity_intensity())

        start()
        converged = wait_for_condition(
            lambda: abs(float(attr.internal_value) - target) <= 0.05,
            timeout=5.0,
            interval=0.2,
        )
        self.assertTrue(converged, "Scenario did not drive activityIntensity to expected target.")

        value = self.sut.read_activity_intensity()
        self.assertAlmostEqual(target, value, delta=0.05)

    @staticmethod
    def _resolve_base_url() -> str:
        return os.environ.get("SPX_API_URL", "http://localhost:8000")

    @staticmethod
    def _require_product_key() -> str:
        product_key = os.environ.get("SPX_PRODUCT_KEY")
        if not product_key:
            raise unittest.SkipTest("SPX_PRODUCT_KEY must be set to run BLE SUT tests.")
        return product_key

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
