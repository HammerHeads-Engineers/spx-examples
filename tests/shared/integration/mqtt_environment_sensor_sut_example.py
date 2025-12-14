# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Hammerheads Engineers Sp. z o.o.
# See the accompanying LICENSE file for terms.

"""Shared integration tests for the SimpleMqttEnvironmentSensorSUT helper."""

from __future__ import annotations

import os
import socket
import time
import unittest
from pathlib import Path
from typing import Callable, Optional

from tests.common.spx_utils import ensure_instance, ensure_model, load_model_definition, wait_for_condition
from tests.devices.mqtt_environment_sensor_sut_example import SimpleMqttEnvironmentSensorSUT

try:
    from paho.mqtt import client as mqtt  # type: ignore
except Exception:  # pragma: no cover - dependency missing in some environments
    mqtt = None  # type: ignore

BROKER_HOST = os.environ.get("MQTT_TEST_BROKER_HOST", "127.0.0.1")
BROKER_PORT = int(os.environ.get("MQTT_TEST_BROKER_PORT", "1883"))
BROKER_CONTAINER_HOST = os.environ.get("MQTT_TEST_BROKER_HOST_CONTAINER")
if BROKER_CONTAINER_HOST is None:
    if os.environ.get("CI"):
        BROKER_CONTAINER_HOST = "mosquitto"
    elif BROKER_HOST in {"127.0.0.1", "localhost"}:
        BROKER_CONTAINER_HOST = "host.docker.internal"
    else:
        BROKER_CONTAINER_HOST = BROKER_HOST
BROKER_CONTAINER_PORT = int(
    os.environ.get("MQTT_TEST_BROKER_PORT_CONTAINER", str(BROKER_PORT))
)
MODEL_PATH = Path("library/domains/iot/generic/environment_sensor__mqtt.yaml")
MODEL_KEY = "tests__generic_mqtt_environment_sensor"
INSTANCE_KEY = "tests_generic_mqtt_environment_sensor_inst"
SPX_API_URL = os.environ.get("SPX_API_URL", "http://localhost:8000")


COMMAND_SETPOINT_TOPIC = "spx/examples/env/command/setpoint_c"


def _broker_available(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except OSError:
        return False


class TestSimpleMqttEnvironmentSensorSUTIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if mqtt is None:
            raise unittest.SkipTest("paho-mqtt is not installed; install it to run MQTT integration tests.")
        if not _broker_available(BROKER_HOST, BROKER_PORT):
            raise unittest.SkipTest(f"MQTT broker not reachable at {BROKER_HOST}:{BROKER_PORT}")

        try:
            import spx_python  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dependency guard
            raise unittest.SkipTest(f"spx_python not installed: {exc}") from exc

        product_key = os.environ.get("SPX_PRODUCT_KEY")
        if not product_key:
            raise unittest.SkipTest("SPX_PRODUCT_KEY must be set to run MQTT integration tests.")

        cls._spx_client = spx_python.init(address=SPX_API_URL, product_key=product_key)
        model_def = load_model_definition(MODEL_PATH)

        model_def["communication"][0]["mqtt"]["broker"] = BROKER_CONTAINER_HOST
        model_def["communication"][0]["mqtt"]["port"] = BROKER_CONTAINER_PORT

        model_changed = ensure_model(cls._spx_client, MODEL_KEY, model_def)

        cls._instance = ensure_instance(
            cls._spx_client,
            INSTANCE_KEY,
            MODEL_KEY,
            recreate=model_changed,
        )

    def setUp(self) -> None:
        self.sut = SimpleMqttEnvironmentSensorSUT(host=BROKER_HOST, port=BROKER_PORT)
        if not self.sut.connect():
            self.skipTest(f"Unable to connect SUT to MQTT broker at {BROKER_HOST}:{BROKER_PORT}")
        time.sleep(0.2)

        self.instance = getattr(self.__class__, "_instance", None)
        if self.instance is None:
            self.skipTest("SPX instance not initialised")
        self.attributes = self.instance["attributes"]

        # Ensure the SPX model has attached to the broker before publishing commands.
        mqtt_connected_attr = self.attributes["mqtt_connected"]
        if mqtt_connected_attr is not None:
            connected = wait_for_condition(
                lambda: bool(float(getattr(mqtt_connected_attr, "internal_value", 0))),
                timeout=10.0,
            )
            self.assertTrue(
                connected,
                "SPX MQTT adapter did not report connected state within timeout.",
            )

        self.publisher = mqtt.Client()
        self.publisher.connect(BROKER_HOST, BROKER_PORT, keepalive=30)
        self.publisher.loop_start()

    def tearDown(self) -> None:
        if hasattr(self, "publisher") and self.publisher is not None:
            try:
                self.publisher.loop_stop()
            except Exception:
                pass
            try:
                self.publisher.disconnect()
            except Exception:
                pass
        if hasattr(self, "sut") and self.sut is not None:
            self.sut.close()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _publish(self, topic: str, payload: str) -> None:
        info = self.publisher.publish(topic, payload, qos=1, retain=False)
        info.wait_for_publish(timeout=2.0)

    def _await_value(
        self,
        getter,
        *,
        timeout: float = 3.0,
        condition: Optional[Callable[[float], bool]] = None,
    ) -> Optional[float]:
        deadline = time.time() + timeout
        last_value: Optional[float] = None
        predicate = condition or (lambda v: True)
        while time.time() < deadline:
            value = getter()
            if value is not None:
                last_value = value
                if predicate(value):
                    return value
            time.sleep(0.1)
        return last_value

    def _wait_for_temperature(self, target: float, *, timeout: float) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            value = float(self.attributes["temperature_c"].internal_value)
            delta = abs(value - target)
            if delta <= 0.5:
                return True
            time.sleep(0.5)
        return False

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------
    def test_receives_temperature_humidity_comfort(self):
        self._publish(SimpleMqttEnvironmentSensorSUT.TEMPERATURE_TOPIC, "26.75")
        self._publish(SimpleMqttEnvironmentSensorSUT.HUMIDITY_TOPIC, "51.2")
        self._publish(SimpleMqttEnvironmentSensorSUT.COMFORT_TOPIC, "89.4")

        temperature = self._await_value(self.sut.latest_temperature)
        humidity = self._await_value(self.sut.latest_humidity)
        comfort = self._await_value(self.sut.latest_comfort_index)

        self.assertIsInstance(temperature, float)
        self.assertAlmostEqual(temperature, 26.75, places=2)
        self.assertIsInstance(humidity, float)
        self.assertAlmostEqual(humidity, 51.2, places=1)
        self.assertIsInstance(comfort, float)
        self.assertAlmostEqual(comfort, 89.4, places=1)

    def test_ignores_non_numeric_payload(self):
        self._publish(SimpleMqttEnvironmentSensorSUT.TEMPERATURE_TOPIC, "22.1")
        baseline = self._await_value(
            self.sut.latest_temperature,
            timeout=2.0,
            condition=lambda v: abs(v - 22.1) <= 0.1,
        )
        self.assertIsInstance(baseline, float)

        self._publish(SimpleMqttEnvironmentSensorSUT.TEMPERATURE_TOPIC, "invalid")
        time.sleep(0.3)
        current = self._await_value(
            self.sut.latest_temperature,
            timeout=1.0,
            condition=lambda v: abs(v - baseline) <= 0.1,
        )
        self.assertIsInstance(current, float)

    def test_setpoint_command_updates_temperature(self):
        start_temp = 20.0
        target_value = 25.0
        self.attributes["temperature_c"].internal_value = start_temp
        self.attributes["target_c"].internal_value = start_temp
        if "temperature_integral" in self.attributes:
            self.attributes["temperature_integral"].internal_value = 0.0
        time.sleep(0.2)

        target_updated = False
        attempts = 3
        for attempt in range(attempts):
            self._publish(COMMAND_SETPOINT_TOPIC, f"{target_value}")
            target_updated = wait_for_condition(
                lambda: abs(self.attributes["target_c"].internal_value - target_value) <= 0.05,
                timeout=5.0,
            )
            if target_updated:
                break
            time.sleep(0.5)

        self.assertTrue(target_updated, f"target_c={self.attributes['target_c'].internal_value} == {target_value} attribute did not update from command topic")

        temp_reached = self._wait_for_temperature(target_value, timeout=10.0)
        self.assertTrue(temp_reached, "temperature_c did not converge to the setpoint")

        telemetry_temperature = self._await_value(
            self.sut.latest_temperature,
            timeout=5.0,
            condition=lambda v: abs(v - target_value) <= 0.5,
        )
        self.assertIsInstance(telemetry_temperature, float)
        self.assertAlmostEqual(telemetry_temperature, target_value, delta=0.5)


if __name__ == "__main__":
    unittest.main()
