# SPDX-License-Identifier: MIT

from __future__ import annotations

import os
import time
import unittest
from typing import Optional

from tests.common.spx_utils import require_existing_instance, wait_for_condition

try:
    from spx_python.unittest_logging import (
        SpxAssertionLoggingMixin,
        spx_append_attribute_value,
        spx_ensure_attribute,
        spx_log_test_case,
    )
except Exception:  # pragma: no cover - optional dependency in some envs
    SpxAssertionLoggingMixin = object  # type: ignore
    spx_append_attribute_value = None  # type: ignore
    spx_ensure_attribute = None  # type: ignore

    def spx_log_test_case(*args, **kwargs):  # type: ignore
        def decorator(func):
            return func

        return decorator


SPX_BASE_URL = os.environ.get("SPX_BASE_URL", "http://localhost:8000")

INSTANCE_KEYS = [
    "spx_hvac_flexit_nordic_bacnet",
    "spx_energy_meter_iem3000_modbus",
    "spx_weather_gateway_wago_pfc200_vaisala_wxt530_mqtt",
    "spx_abb_sa_s12_16_5_1_knx",
    "spx_abb_jra_s4_230_5_1_knx",
]

ABB_SWITCH_ATTRS = [
    "ch01",
    "ch02",
    "ch03",
    "ch04",
]
ABB_COVER_POS_ATTRS = [
    "c1_position_pct",
    "c2_position_pct",
    "c3_position_pct",
    "c4_position_pct",
]
ABB_COVER_TRAVEL_ATTRS = [
    "c1_travel_time_s",
    "c2_travel_time_s",
    "c3_travel_time_s",
    "c4_travel_time_s",
]
BRIGHTNESS_THRESHOLD = 5000.0
BRIGHTNESS_LOW = 1000.0
BRIGHTNESS_HIGH = 6000.0


def _instance_state(instance) -> Optional[str]:
    try:
        state = instance.state
    except Exception:
        state = None
    if isinstance(state, str):
        return state

    try:
        doc = instance.get()
    except Exception:
        doc = None
    if isinstance(doc, dict):
        value = doc.get("state")
        if isinstance(value, str):
            return value
        attr = doc.get("attr")
        if isinstance(attr, dict):
            state_attr = attr.get("state")
            if isinstance(state_attr, dict):
                value = state_attr.get("value")
                if isinstance(value, str):
                    return value
    return None


def _spx_attr_float(attr) -> Optional[float]:
    try:
        value = attr.internal_value
    except Exception:
        value = None
    if value is None:
        value = attr
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _spx_attr_int(attr) -> Optional[int]:
    try:
        value = attr.internal_value
    except Exception:
        value = None
    if value is None:
        value = attr
    if isinstance(value, bool):
        return 1 if value else 0
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


class TestSmartBuildingPackInstancesRunning(SpxAssertionLoggingMixin, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import spx_python  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise unittest.SkipTest(f"spx_python not available: {exc}") from exc

        product_key = os.environ.get("SPX_PRODUCT_KEY")
        if not product_key:
            raise unittest.SkipTest("SPX_PRODUCT_KEY must be set to run integration tests.")

        cls._client = spx_python.init(address=SPX_BASE_URL, product_key=product_key)
        cls._instances = {
            key: require_existing_instance(cls._client, key, ensure_running=False)
            for key in INSTANCE_KEYS
        }
        cls._logging_enabled = spx_ensure_attribute is not None and spx_append_attribute_value is not None
        cls.spx_log_attr = "test_logs"
        cls.spx_log_instance = None
        if cls._logging_enabled:
            cls._log_instance = cls._instances["spx_weather_gateway_wago_pfc200_vaisala_wxt530_mqtt"]
            spx_ensure_attribute(cls._log_instance, cls.spx_log_attr, default=[])
            cls.spx_log_instance = cls._log_instance
            cls._log_start_ts = time.time()

    def _log_step(self, event: str, **meta: object) -> None:
        if not getattr(self, "_logging_enabled", False):
            return
        if not spx_append_attribute_value or not getattr(self, "spx_log_instance", None):
            return
        payload = {"ts": time.time(), "kind": "step", "event": event}
        payload.update(meta)
        spx_append_attribute_value(self.spx_log_instance, self.spx_log_attr, payload)

    def _recent_logs(self):
        if not getattr(self, "_logging_enabled", False):
            self.skipTest("spx-python logging helpers are unavailable.")
        instance = getattr(self, "spx_log_instance", None)
        if instance is None:
            self.skipTest("Logging instance unavailable.")
        try:
            entries = list(instance["attributes"][self.spx_log_attr].internal_value or [])
        except Exception as exc:
            self.fail(f"Unable to read test_logs from SPX instance: {exc}")
        start_ts = getattr(self, "_log_start_ts", 0.0)
        return [entry for entry in entries if isinstance(entry, dict) and entry.get("ts", 0.0) >= start_ts]

    @spx_log_test_case()
    def test_start_instances_are_running(self):
        for key, instance in self._instances.items():
            last_state = [None]

            def _is_running() -> bool:
                last_state[0] = _instance_state(instance)
                return (last_state[0] or "").lower() == "running"

            ready = wait_for_condition(_is_running, timeout=10.0, interval=0.2)
            self.assertTrue(
                ready,
                f"Expected '{key}' to be RUNNING, got '{last_state[0]}'",
            )
            self._log_step("instance_state", instance=key, state=last_state[0])

    @spx_log_test_case()
    def test_homeassistant_outdoor_lights_automation(self):
        weather_instance = self._instances["spx_weather_gateway_wago_pfc200_vaisala_wxt530_mqtt"]
        if (_instance_state(weather_instance) or "").lower() != "running":
            try:
                weather_instance.start()
            except Exception:
                pass

        switch_instance = self._instances["spx_abb_sa_s12_16_5_1_knx"]
        if (_instance_state(switch_instance) or "").lower() != "running":
            try:
                switch_instance.start()
            except Exception:
                pass

        cover_instance = self._instances["spx_abb_jra_s4_230_5_1_knx"]
        if (_instance_state(cover_instance) or "").lower() != "running":
            try:
                cover_instance.start()
            except Exception:
                pass

        attrs = weather_instance["attributes"]
        brightness_attr = attrs["brightness_lux"]
        initial_brightness = _spx_attr_float(brightness_attr)
        if initial_brightness is None:
            self.fail("Could not read initial brightness_lux from SPX weather instance.")
        self._log_step("brightness_initial", value=initial_brightness)

        switch_attrs = switch_instance["attributes"]
        cover_attrs = cover_instance["attributes"]

        try:
            invert_position = _spx_attr_int(cover_attrs["invert_position"]) or 0
        except Exception:
            invert_position = 0
        open_target = 100.0 if invert_position == 1 else 0.0
        try:
            position_tolerance = _spx_attr_float(cover_attrs["position_tolerance_pct"])
        except Exception:
            position_tolerance = None
        if position_tolerance is None:
            position_tolerance = 1.0

        travel_times = []
        for attr_name in ABB_COVER_TRAVEL_ATTRS:
            try:
                value = _spx_attr_float(cover_attrs[attr_name])
            except Exception:
                value = None
            if value is not None:
                travel_times.append(value)
        cover_timeout = max(travel_times) + 5.0 if travel_times else 20.0
        self._log_step(
            "cover_config",
            invert_position=invert_position,
            open_target=open_target,
            position_tolerance=position_tolerance,
            timeout_s=cover_timeout,
        )

        def _set_brightness(value: float) -> None:
            if hasattr(brightness_attr, "internal_value"):
                brightness_attr.internal_value = value
            else:
                weather_instance.put_attr("attributes/brightness_lux", value)

        def _wait_for_switches(expected_value: int) -> dict[str, Optional[int]]:
            last_values: dict[str, Optional[int]] = {}
            last_error = [None]

            def _ready() -> bool:
                try:
                    for attr_name in ABB_SWITCH_ATTRS:
                        last_values[attr_name] = _spx_attr_int(switch_attrs[attr_name])
                except Exception as exc:
                    last_error[0] = exc
                    return False
                return all(value == expected_value for value in last_values.values())

            ready = wait_for_condition(_ready, timeout=15.0, interval=0.5)
            if not ready and last_error[0] is not None:
                self.fail(f"Failed to read ABB switch attributes: {last_error[0]}")
            if not ready:
                self.fail(
                    f"Expected ABB switch attributes {expected_value}, got {last_values}"
                )
            return last_values

        def _wait_for_blinds_open() -> dict[str, Optional[float]]:
            last_positions: dict[str, Optional[float]] = {}
            last_error = [None]

            def _ready() -> bool:
                try:
                    for attr_name in ABB_COVER_POS_ATTRS:
                        last_positions[attr_name] = _spx_attr_float(cover_attrs[attr_name])
                except Exception as exc:
                    last_error[0] = exc
                    return False
                for value in last_positions.values():
                    if value is None:
                        return False
                    if abs(value - open_target) > position_tolerance:
                        return False
                return True

            ready = wait_for_condition(_ready, timeout=cover_timeout, interval=0.5)
            if not ready and last_error[0] is not None:
                self.fail(f"Failed to read ABB cover attributes: {last_error[0]}")
            if not ready:
                self.fail(
                    "Expected ABB covers open "
                    f"(target {open_target}±{position_tolerance}), got {last_positions}"
                )
            return last_positions

        if initial_brightness < BRIGHTNESS_THRESHOLD:
            first_value = BRIGHTNESS_HIGH
            first_expected = 0
            second_value = BRIGHTNESS_LOW
            second_expected = 1
        else:
            first_value = BRIGHTNESS_LOW
            first_expected = 1
            second_value = BRIGHTNESS_HIGH
            second_expected = 0

        try:
            _set_brightness(first_value)
            self._log_step("set_brightness", value=first_value)
            switch_states = _wait_for_switches(first_expected)
            self._log_step("switches_state", expected=first_expected, actual=switch_states)
            cover_positions = _wait_for_blinds_open()
            self._log_step("blinds_state", expected=open_target, actual=cover_positions)

            _set_brightness(second_value)
            self._log_step("set_brightness", value=second_value)
            switch_states = _wait_for_switches(second_expected)
            self._log_step("switches_state", expected=second_expected, actual=switch_states)
            cover_positions = _wait_for_blinds_open()
            self._log_step("blinds_state", expected=open_target, actual=cover_positions)

        finally:
            try:
                _set_brightness(initial_brightness)
            except Exception:
                pass

    @spx_log_test_case()
    def test_z_test_logs_recorded(self):
        entries = self._recent_logs()
        self.assertIsInstance(entries, list)
        self.assertTrue(entries, "Expected test_logs entries to be recorded.")

        testcase_end = [
            entry
            for entry in entries
            if entry.get("kind") == "testcase" and entry.get("event") == "end"
        ]
        testcase_names = {entry.get("name") for entry in testcase_end}
        for expected in (
            "test_start_instances_are_running",
            "test_homeassistant_outdoor_lights_automation",
        ):
            self.assertIn(expected, testcase_names, f"Missing testcase end log for '{expected}'.")

        step_events = {entry.get("event") for entry in entries if entry.get("kind") == "step"}
        for expected in ("set_brightness", "switches_state", "blinds_state"):
            self.assertIn(expected, step_events, f"Missing step log '{expected}'.")
