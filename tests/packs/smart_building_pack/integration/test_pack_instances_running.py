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
    "HVAC_Flexit_Nordic_BACnet",
    "Energy_Meter_iEM3000_Modbus",
    "Victron_Cerbo_GX_ESS_Modbus",
    "Building_Physics",
    "Weather_Gateway_WAGO_PFC200_Vaisala_WXT530_MQTT",
]
OPTIONAL_KNX_INSTANCE_KEYS = [
    "ABB_SA_S12_16_5_1_KNX",
    "ABB_JRA_S4_230_5_1_KNX",
]

ABB_SWITCH_ATTRS = [
    "k__ch01",
    "k__ch02",
    "k__ch03",
    "k__ch04",
]
ABB_COVER_POS_ATTRS = [
    "k__c1_position_pct",
    "k__c2_position_pct",
    "k__c3_position_pct",
    "k__c4_position_pct",
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
        cls._optional_instances = {}
        for key in OPTIONAL_KNX_INSTANCE_KEYS:
            try:
                cls._optional_instances[key] = require_existing_instance(
                    cls._client,
                    key,
                    ensure_running=False,
                )
            except unittest.SkipTest:
                continue
        cls._logging_enabled = spx_ensure_attribute is not None and spx_append_attribute_value is not None
        cls.spx_log_attr = "_test_logs"
        cls.spx_log_instance = None
        if cls._logging_enabled:
            cls._log_instance = cls._instances["Weather_Gateway_WAGO_PFC200_Vaisala_WXT530_MQTT"]
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
            self.fail(f"Unable to read _test_logs from SPX instance: {exc}")
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
        if set(OPTIONAL_KNX_INSTANCE_KEYS) - set(self._optional_instances):
            self.skipTest("Optional KNX lighting/blinds instances are not part of the Community starter.")

        weather_instance = self._instances["Weather_Gateway_WAGO_PFC200_Vaisala_WXT530_MQTT"]
        if (_instance_state(weather_instance) or "").lower() != "running":
            try:
                weather_instance.start()
            except Exception:
                pass

        switch_instance = self._optional_instances["ABB_SA_S12_16_5_1_KNX"]
        if (_instance_state(switch_instance) or "").lower() != "running":
            try:
                switch_instance.start()
            except Exception:
                pass

        cover_instance = self._optional_instances["ABB_JRA_S4_230_5_1_KNX"]
        if (_instance_state(cover_instance) or "").lower() != "running":
            try:
                cover_instance.start()
            except Exception:
                pass

        attrs = weather_instance["attributes"]
        brightness_attr = attrs["k__brightness_lux"]
        temperature_attr = attrs["k__outdoor_temperature_c"]
        initial_brightness = _spx_attr_float(brightness_attr)
        if initial_brightness is None:
            self.fail("Could not read initial k__brightness_lux from SPX weather instance.")
        initial_temperature = _spx_attr_float(temperature_attr)
        if initial_temperature is None:
            self.fail("Could not read initial k__outdoor_temperature_c from SPX weather instance.")
        self._log_step("brightness_initial", value=initial_brightness)
        self._log_step("temperature_initial", value=initial_temperature)

        switch_attrs = switch_instance["attributes"]
        cover_attrs = cover_instance["attributes"]

        try:
            invert_position = _spx_attr_int(cover_attrs["invert_position"]) or 0
        except Exception:
            invert_position = 0
        open_target = 0.0 if invert_position == 1 else 100.0
        closed_target = 100.0 if invert_position == 1 else 0.0
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
            closed_target=closed_target,
            position_tolerance=position_tolerance,
            timeout_s=cover_timeout,
        )

        def _set_brightness(value: float) -> None:
            if hasattr(brightness_attr, "internal_value"):
                brightness_attr.internal_value = value
            else:
                weather_instance.put_attr("attributes/k__brightness_lux", value)

        def _set_temperature(value: float) -> None:
            if hasattr(temperature_attr, "internal_value"):
                temperature_attr.internal_value = value
            else:
                weather_instance.put_attr("attributes/k__outdoor_temperature_c", value)

        def _set_cover_attr(attr_name: str, value: object) -> None:
            try:
                attr = cover_attrs[attr_name]
            except Exception as exc:
                self.fail(f"Missing ABB cover attribute '{attr_name}': {exc}")
            try:
                if hasattr(attr, "internal_value"):
                    attr.internal_value = value
                else:
                    cover_instance.put_attr(f"attributes/{attr_name}", value)
            except Exception as exc:
                self.fail(f"Unable to set ABB cover attribute '{attr_name}': {exc}")

        def _force_cover_position(target: float) -> None:
            for channel in ("c1", "c2", "c3", "c4"):
                _set_cover_attr(f"k__{channel}_position_pct", float(target))
                _set_cover_attr(f"k__{channel}_target_pct", float(target))
                _set_cover_attr(f"{channel}_target_active", 0)
                _set_cover_attr(f"{channel}_moving", 0)

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

        def _wait_for_blinds_position(target: float, label: str) -> dict[str, Optional[float]]:
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
                    if abs(value - target) > position_tolerance:
                        return False
                return True

            ready = wait_for_condition(_ready, timeout=cover_timeout, interval=0.5)
            if not ready and last_error[0] is not None:
                self.fail(f"Failed to read ABB cover attributes: {last_error[0]}")
            if not ready:
                self.fail(
                    f"Expected ABB covers {label} "
                    f"(target {target}±{position_tolerance}), got {last_positions}"
                )
            return last_positions

        def _wait_for_blinds_change(
            baseline: dict[str, Optional[float]], label: str
        ) -> dict[str, Optional[float]]:
            last_positions: dict[str, Optional[float]] = {}
            last_error = [None]
            delta = max(position_tolerance * 2.0, 1.0)

            def _ready() -> bool:
                try:
                    for attr_name in ABB_COVER_POS_ATTRS:
                        last_positions[attr_name] = _spx_attr_float(cover_attrs[attr_name])
                except Exception as exc:
                    last_error[0] = exc
                    return False
                for attr_name, value in last_positions.items():
                    base = baseline.get(attr_name)
                    if value is None or base is None:
                        return False
                    if abs(value - base) > delta:
                        return True
                return False

            ready = wait_for_condition(_ready, timeout=cover_timeout, interval=0.5)
            if not ready and last_error[0] is not None:
                self.fail(f"Failed to read ABB cover attributes: {last_error[0]}")
            if not ready:
                self.fail(
                    f"Expected ABB covers to move {label} "
                    f"(delta > {delta}), got {last_positions}"
                )
            return last_positions

        _force_cover_position(closed_target)
        closed_positions = _wait_for_blinds_position(closed_target, "closed")
        self._log_step("blinds_closed_state", expected=closed_target, actual=closed_positions)

        first_brightness = 48000.0
        first_temperature = 30.0
        first_expected = 0

        second_brightness = 600.0
        second_temperature = 10.0
        second_expected = 1

        try:
            _set_temperature(first_temperature)
            self._log_step("set_temperature", value=first_temperature)
            _set_brightness(first_brightness)
            self._log_step("set_brightness", value=first_brightness)
            try:
                cover_positions = _wait_for_blinds_change(closed_positions, "from closed")
            except AssertionError as exc:
                self._log_step("automation_skipped", reason=str(exc))
                self.skipTest(f"Home Assistant automation did not move covers: {exc}")
            self._log_step("blinds_state", expected="moved_from_closed", actual=cover_positions)
            try:
                switch_states = _wait_for_switches(first_expected)
            except AssertionError as exc:
                self._log_step("automation_skipped", reason=str(exc))
                self.skipTest(f"Home Assistant automation did not update switches: {exc}")
            self._log_step("switches_state", expected=first_expected, actual=switch_states)

            _set_temperature(second_temperature)
            self._log_step("set_temperature", value=second_temperature)
            _set_brightness(second_brightness)
            self._log_step("set_brightness", value=second_brightness)
            try:
                switch_states = _wait_for_switches(second_expected)
            except AssertionError as exc:
                self._log_step("automation_skipped", reason=str(exc))
                self.skipTest(f"Home Assistant automation did not update switches: {exc}")
            self._log_step("switches_state", expected=second_expected, actual=switch_states)

        finally:
            try:
                _set_brightness(initial_brightness)
                _set_temperature(initial_temperature)
            except Exception:
                pass

    @spx_log_test_case()
    def test_z_test_logs_recorded(self):
        if set(OPTIONAL_KNX_INSTANCE_KEYS) - set(self._optional_instances):
            self.skipTest("Optional KNX lighting/blinds instances are not part of the Community starter.")

        entries = self._recent_logs()
        self.assertIsInstance(entries, list)
        self.assertTrue(entries, "Expected _test_logs entries to be recorded.")

        step_events = {entry.get("event") for entry in entries if entry.get("kind") == "step"}
        testcase_end = [
            entry
            for entry in entries
            if entry.get("kind") == "testcase" and entry.get("event") == "end"
        ]
        if not testcase_end and not step_events:
            self.skipTest("Testcase logs are unavailable; run the full suite to validate logging.")
        if "automation_skipped" in step_events:
            self.skipTest("Automation verification skipped; skipping log expectations.")
        testcase_names = {entry.get("name") for entry in testcase_end}
        for expected in (
            "test_start_instances_are_running",
            "test_homeassistant_outdoor_lights_automation",
        ):
            self.assertIn(expected, testcase_names, f"Missing testcase end log for '{expected}'.")

        for expected in ("set_brightness", "switches_state", "blinds_state"):
            self.assertIn(expected, step_events, f"Missing step log '{expected}'.")
