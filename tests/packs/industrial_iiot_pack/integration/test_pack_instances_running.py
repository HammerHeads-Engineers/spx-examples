# SPDX-License-Identifier: MIT

from __future__ import annotations

import os
import unittest
from typing import Optional

from tests.common.spx_utils import require_existing_instance, wait_for_condition


SPX_BASE_URL = os.environ.get("SPX_BASE_URL", "http://localhost:8000")

INSTANCE_KEYS = [
    "spx_eurotherm_3216_temp",
    "spx_eurotherm_3504_pressure",
    "spx_g120c_vfd",
    "spx_wago_750_8000_io",
    "spx_s7_1500_process_cell",
]


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


def _float_attr(attr) -> Optional[float]:
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


class TestIndustrialPackInstancesRunning(unittest.TestCase):
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

    def test_eurotherm_setpoints_are_independent(self):
        euro_3216 = self._instances["spx_eurotherm_3216_temp"]
        euro_3504 = self._instances["spx_eurotherm_3504_pressure"]

        attrs_3216 = euro_3216["attributes"]
        attrs_3504 = euro_3504["attributes"]

        baseline_pressure = _float_attr(attrs_3504["pressure_sp_bar"])
        self.assertIsNotNone(baseline_pressure, "Unable to read Eurotherm 3504 pressure setpoint.")

        attrs_3216["auto_man_raw"].internal_value = 0
        attrs_3216["target_sp_raw"].internal_value = 600

        temp_ready = wait_for_condition(
            lambda: abs((_float_attr(attrs_3216["setpoint_c"]) or 0.0) - 60.0) <= 0.1,
            timeout=5.0,
            interval=0.2,
        )
        self.assertTrue(temp_ready, "Eurotherm 3216 setpoint did not reach 60.0 C.")

        pressure_after_temp = _float_attr(attrs_3504["pressure_sp_bar"])
        self.assertIsNotNone(pressure_after_temp, "Unable to read Eurotherm 3504 pressure setpoint.")
        self.assertTrue(
            abs(pressure_after_temp - baseline_pressure) <= 0.05,
            "Eurotherm 3504 setpoint changed while updating Eurotherm 3216.",
        )

        baseline_temp = _float_attr(attrs_3216["setpoint_c"])
        self.assertIsNotNone(baseline_temp, "Unable to read Eurotherm 3216 temperature setpoint.")

        attrs_3504["auto_man_raw"].internal_value = 0
        attrs_3504["target_sp_raw"].internal_value = 25

        pressure_ready = wait_for_condition(
            lambda: abs((_float_attr(attrs_3504["pressure_sp_bar"]) or 0.0) - 2.5) <= 0.05,
            timeout=5.0,
            interval=0.2,
        )
        self.assertTrue(pressure_ready, "Eurotherm 3504 setpoint did not reach 2.5 bar.")

        temp_after_pressure = _float_attr(attrs_3216["setpoint_c"])
        self.assertIsNotNone(temp_after_pressure, "Unable to read Eurotherm 3216 temperature setpoint.")
        self.assertTrue(
            abs(temp_after_pressure - baseline_temp) <= 0.1,
            "Eurotherm 3216 setpoint changed while updating Eurotherm 3504.",
        )

    def test_drive_io_opcua_commands_are_independent(self):
        g120c = self._instances["spx_g120c_vfd"]
        wago = self._instances["spx_wago_750_8000_io"]
        s7 = self._instances["spx_s7_1500_process_cell"]

        g120c_attrs = g120c["attributes"]
        wago_attrs = wago["attributes"]
        s7_attrs = s7["attributes"]

        g120c_attrs["control_word_raw"].internal_value = 79
        g120c_attrs["speed_setpoint_raw"].internal_value = 30

        drive_ready = wait_for_condition(
            lambda: (_float_attr(g120c_attrs["speed_actual_hz"]) or 0.0) > 0.5,
            timeout=8.0,
            interval=0.2,
        )
        self.assertTrue(drive_ready, "G120C did not ramp the actual speed above 0.5 Hz.")

        wago_attrs["do_1"].internal_value = 1
        io_ready = wait_for_condition(
            lambda: int(round(_float_attr(wago_attrs["do_1"]) or 0.0)) == 1,
            timeout=2.0,
            interval=0.2,
        )
        self.assertTrue(io_ready, "WAGO DO1 did not update to 1.")

        s7_attrs["pump_command_percent"].internal_value = 60.0
        pump_ready = wait_for_condition(
            lambda: abs((_float_attr(s7_attrs["pump_speed_percent"]) or 0.0) - 60.0) <= 5.0,
            timeout=8.0,
            interval=0.2,
        )
        self.assertTrue(pump_ready, "S7-1500 pump speed did not track the command.")
