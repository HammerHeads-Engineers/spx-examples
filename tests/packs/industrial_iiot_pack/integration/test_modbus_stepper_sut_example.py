# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Hammerheads Engineers Sp. z o.o.
# See the accompanying LICENSE file for terms.

"""Integration coverage for the example Modbus stepper SUT device implementation."""

import contextlib
import os
import time
import unittest
from typing import Optional

from tests.common.spx_utils import bootstrap_model_instance, wait_seconds
from tests.common.repo import repo_root
from tests.devices.modbus_stepper_sut_example import ModbusStepperSUTExample, ModbusTcpClient

ROOT = repo_root()
MODEL_PATH = (
    ROOT
    / "library"
    / "domains"
    / "motion_controllers"
    / "generic"
    / "stepper_controller__modbus.yaml"
)
MODEL_KEY = "tests__stepper_controller"
INSTANCE_KEY = "generic_stepper_controller"
DISCONNECT_DURATION = 1.5
SPX_API_URL = os.environ.get("SPX_API_URL", "http://localhost:8000")


class TestModbusStepperSUTExampleIntegration(unittest.TestCase):
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

    def _make_sut_example(self, **kwargs):
        return ModbusStepperSUTExample(unit_id=1, **kwargs)

    @contextlib.contextmanager
    def _connected_sut_example(self, **kwargs):
        sut = self._make_sut_example(**kwargs)
        try:
            if not sut.connect():
                self.skipTest(
                    "Modbus server not reachable at 127.0.0.1:502 (unit 2)"
                )
            yield sut
        finally:
            sut.close()

    def _require_spx_instance(self):
        instance = getattr(self.__class__, "_instance", None)
        if instance is None:  # pragma: no cover - defensive
            self.skipTest("Stepper controller instance not initialised")
        return instance

    @staticmethod
    def _configure_disconnect_scenario(scenarios, duration: float = DISCONNECT_DURATION):
        scenarios["modbus_disconnect"] = {
            "enabled": True,
            "duration": duration,
            "call": {
                "path": "communication.modbus_tcp.detach",
                "stop_path": "communication.modbus_tcp.attach",
            },
        }
        return scenarios["modbus_disconnect"]

    @staticmethod
    def _bool_attribute(attribute) -> bool:
        return bool(round(float(attribute.internal_value)))

    def _reset_stepper_state(
        self,
        attributes,
        *,
        position: float = 0.0,
        soft_limit_pos: Optional[float] = None,
        soft_limit_neg: Optional[float] = None,
    ) -> None:
        attributes["position_command"].internal_value = position
        attributes["position_feedback"].internal_value = position
        attributes["velocity_command"].internal_value = 0.0
        attributes["velocity_feedback"].internal_value = 0.0
        attributes["motion_error"].internal_value = 0.0
        attributes["pos_limit_switch"].internal_value = 0
        attributes["neg_limit_switch"].internal_value = 0
        attributes["alarm_limit"].internal_value = 0
        if soft_limit_pos is not None:
            attributes["soft_limit_pos"].internal_value = soft_limit_pos
        if soft_limit_neg is not None:
            attributes["soft_limit_neg"].internal_value = soft_limit_neg
        wait_seconds(0.2)

    def _await_position_feedback(
        self,
        sut: ModbusStepperSUTExample,
        feedback_attribute,
        *,
        target: float,
        timeout: float,
        tolerance: float = 1.0,
    ):
        deadline = time.time() + timeout
        last_error = None
        recovered_position = None
        final_expected = None

        while time.time() < deadline:
            wait_seconds(0.5)
            final_expected = float(feedback_attribute.internal_value)
            try:
                recovered_position = sut.read_position_feedback()
            except RuntimeError as exc:
                last_error = exc
                continue

            reached_target = (
                final_expected >= target if target >= 0 else final_expected <= target
            )
            if reached_target and abs(recovered_position - final_expected) <= tolerance:
                return recovered_position, final_expected

        state = sut.state()
        details = [f"sut_state={state}"]
        if last_error:
            details.append(f"last_error={last_error}")
        if final_expected is not None:
            details.append(
                f"expected_position={final_expected}, sut_read={recovered_position}"
            )
        detail_msg = ", ".join(details)
        raise AssertionError(
            f"Modbus SUT did not recover within {timeout}s ({detail_msg})"
        )

    def _await_limit_switch(self, attribute, expected: int, timeout: float = 5.0) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._bool_attribute(attribute) == bool(expected):
                return
            wait_seconds(0.1)
        raise AssertionError(
            f"Limit switch did not reach state {expected} within {timeout}s"
        )

    @contextlib.contextmanager
    def _running_scenario(self, scenario):
        try:
            scenario.start()
            yield
        finally:
            pass

    def test_connects_default_instance(self):
        sut = self._make_sut_example()
        try:
            connected = sut.connect()
            self.assertTrue(
                connected,
                "Expected connection to Modbus server at 127.0.0.1:502 (unit 1)",
            )
        finally:
            sut.close()

    def test_reads_position_feedback(self):
        sut = self._make_sut_example()
        try:
            if not sut.connect():
                self.skipTest(
                    "Modbus server not reachable at 127.0.0.1:502 (unit 1)"
                )
            try:
                position = sut.read_position_feedback()
            except RuntimeError as exc:
                self.skipTest(f"Unable to read position feedback: {exc}")
        finally:
            sut.close()

        self.assertIsInstance(
            position, float, "Expected position feedback to be a float value"
        )

    def test_timeout_behavior(self):
        with self._connected_sut_example(timeout=1.0, retries=3) as sut:
            instance = self._require_spx_instance()
            attributes = instance["attributes"]
            feedback_attr = attributes["position_feedback"]

            scenario = self._configure_disconnect_scenario(instance["scenarios"])

            position = sut.read_position_feedback()
            self.assertIsInstance(
                position, float, "Expected position feedback to be a float value"
            )
            self.assertEqual(
                sut.state(),
                "connected",
                f"Expected SUT to be connected, got '{sut.state()}'",
            )

            with self._running_scenario(scenario):
                attributes["max_speed"].internal_value = 100  # limit travel speed
                attributes["position_command"].internal_value = 200  # move target
                attributes["max_accel"].internal_value = 50  # limit accel
                attributes["max_decel"].internal_value = 50  # limit decel

                wait_seconds(duration=DISCONNECT_DURATION + 0.5)  # duration + buffer

                sut_position, expected_position = self._await_position_feedback(
                    sut,
                    feedback_attr,
                    target=190.0,
                    timeout=20.0,
                    tolerance=1.0,
                )

            self.assertGreaterEqual(
                expected_position,
                190.0,
                "Stepper model did not reach target position within recovery window",
            )
            self.assertAlmostEqual(
                sut_position,
                expected_position,
                delta=1.0,
                msg="SUT did not report the latest position feedback value",
            )
            self.assertEqual(
                sut.state(),
                "connected",
                f"Expected SUT to be connected after recovery, got '{sut.state()}'",
            )

    def test_moves_to_positive_position(self):
        with self._connected_sut_example(timeout=1.0, retries=3) as sut:
            instance = self._require_spx_instance()
            attributes = instance["attributes"]
            sut.set_enable(1)
            original_limits = {
                "max_speed": float(attributes["max_speed"].internal_value),
                "max_accel": float(attributes["max_accel"].internal_value),
                "max_decel": float(attributes["max_decel"].internal_value),
            }
            self._reset_stepper_state(attributes, position=0.0)
            sut.set_motion_limits(max_speed=80.0, max_accel=40.0, max_decel=40.0)

            try:
                sut.set_position_command(150.0)
                sut_position, expected_position = self._await_position_feedback(
                    sut,
                    attributes["position_feedback"],
                    target=149.0,
                    timeout=15.0,
                    tolerance=1.0,
                )
                wait_seconds(0.5)
                self.assertAlmostEqual(expected_position, 150.0, delta=1.0)
                self.assertAlmostEqual(sut_position, expected_position, delta=1.0)
                self.assertFalse(self._bool_attribute(attributes["pos_limit_switch"]))
                self.assertFalse(self._bool_attribute(attributes["neg_limit_switch"]))
            finally:
                self._reset_stepper_state(attributes)
                sut.set_position_command(0.0)
                sut.set_motion_limits(
                    max_speed=original_limits["max_speed"],
                    max_accel=original_limits["max_accel"],
                    max_decel=original_limits["max_decel"],
                )
                wait_seconds(0.2)

    def test_moves_to_negative_position(self):
        with self._connected_sut_example(timeout=1.0, retries=3) as sut:
            instance = self._require_spx_instance()
            attributes = instance["attributes"]
            sut.set_enable(1)
            original_limits = {
                "max_speed": float(attributes["max_speed"].internal_value),
                "max_accel": float(attributes["max_accel"].internal_value),
                "max_decel": float(attributes["max_decel"].internal_value),
            }
            self._reset_stepper_state(attributes, position=40.0)
            sut.set_motion_limits(max_speed=80.0, max_accel=40.0, max_decel=40.0)

            try:
                sut.set_position_command(-8.0)
                sut_position, expected_position = self._await_position_feedback(
                    sut,
                    attributes["position_feedback"],
                    target=-7.5,
                    timeout=15.0,
                    tolerance=1.0,
                )
                wait_seconds(0.5)
                self.assertAlmostEqual(expected_position, -8.0, delta=1.0)
                self.assertAlmostEqual(sut_position, expected_position, delta=1.0)
                self.assertFalse(self._bool_attribute(attributes["pos_limit_switch"]))
                self.assertFalse(self._bool_attribute(attributes["neg_limit_switch"]))
            finally:
                self._reset_stepper_state(attributes)
                sut.set_position_command(0.0)
                sut.set_motion_limits(
                    max_speed=original_limits["max_speed"],
                    max_accel=original_limits["max_accel"],
                    max_decel=original_limits["max_decel"],
                )
                wait_seconds(0.2)

    def test_soft_limit_positive_enforced(self):
        with self._connected_sut_example(timeout=1.0, retries=3) as sut:
            instance = self._require_spx_instance()
            attributes = instance["attributes"]
            sut.set_enable(1)
            original_pos_limit = float(attributes["soft_limit_pos"].internal_value)
            original_limits = {
                "max_speed": float(attributes["max_speed"].internal_value),
                "max_accel": float(attributes["max_accel"].internal_value),
                "max_decel": float(attributes["max_decel"].internal_value),
            }
            sut.set_motion_limits(max_speed=80.0, max_accel=40.0, max_decel=40.0)

            try:
                self._reset_stepper_state(attributes, position=0.0, soft_limit_pos=30.0)

                sut.set_position_command(100.0)
                sut_position, expected_position = self._await_position_feedback(
                    sut,
                    attributes["position_feedback"],
                    target=29.0,
                    timeout=10.0,
                    tolerance=0.5,
                )
                self._await_limit_switch(attributes["pos_limit_switch"], 1)
                self.assertAlmostEqual(expected_position, 30.0, delta=0.5)
                self.assertAlmostEqual(sut_position, expected_position, delta=0.5)
                self.assertFalse(self._bool_attribute(attributes["neg_limit_switch"]))
            finally:
                self._reset_stepper_state(
                    attributes,
                    soft_limit_pos=original_pos_limit,
                )
                sut.set_position_command(0.0)
                sut.set_motion_limits(
                    max_speed=original_limits["max_speed"],
                    max_accel=original_limits["max_accel"],
                    max_decel=original_limits["max_decel"],
                )
                wait_seconds(0.2)

    def test_soft_limit_negative_enforced(self):
        with self._connected_sut_example(timeout=1.0, retries=3) as sut:
            instance = self._require_spx_instance()
            attributes = instance["attributes"]
            sut.set_enable(1)
            original_neg_limit = float(attributes["soft_limit_neg"].internal_value)
            original_limits = {
                "max_speed": float(attributes["max_speed"].internal_value),
                "max_accel": float(attributes["max_accel"].internal_value),
                "max_decel": float(attributes["max_decel"].internal_value),
            }
            sut.set_motion_limits(max_speed=80.0, max_accel=40.0, max_decel=40.0)

            try:
                self._reset_stepper_state(attributes, position=0.0, soft_limit_neg=-5.0)

                sut.set_position_command(-25.0)
                sut_position, expected_position = self._await_position_feedback(
                    sut,
                    attributes["position_feedback"],
                    target=-4.8,
                    timeout=10.0,
                    tolerance=0.5,
                )
                self._await_limit_switch(attributes["neg_limit_switch"], 1)
                self.assertAlmostEqual(expected_position, -5.0, delta=0.5)
                self.assertAlmostEqual(sut_position, expected_position, delta=0.5)
                self.assertFalse(self._bool_attribute(attributes["pos_limit_switch"]))
            finally:
                self._reset_stepper_state(
                    attributes,
                    soft_limit_neg=original_neg_limit,
                )
                sut.set_position_command(0.0)
                sut.set_motion_limits(
                    max_speed=original_limits["max_speed"],
                    max_accel=original_limits["max_accel"],
                    max_decel=original_limits["max_decel"],
                )
                wait_seconds(0.2)

    def test_timeout_single_retry_disabled(self):
        with self._connected_sut_example(timeout=0.0, retries=0) as sut:
            instance = self._require_spx_instance()
            attributes = instance["attributes"]

            scenario = self._configure_disconnect_scenario(instance["scenarios"])

            with self._running_scenario(scenario):
                attributes["position_command"].internal_value = 250

                failure_deadline = time.time() + 3.0
                while time.time() < failure_deadline:
                    try:
                        sut.read_position_feedback()
                    except RuntimeError:
                        break
                    wait_seconds(0.1)
                else:
                    self.fail(
                        "Expected SUT without retries to fail on first disconnect read"
                    )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
