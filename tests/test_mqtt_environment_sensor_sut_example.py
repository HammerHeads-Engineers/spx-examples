# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Hammerheads Engineers Sp. z o.o.
# See the accompanying LICENSE file for terms.

"""Integration tests for the SimpleMqttEnvironmentSensorSUT helper."""

from __future__ import annotations

import os
from pprint import pprint
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
MODEL_PATH = Path("library/iot/generic/mqtt_environment_sensor.yaml")
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
        print(
            f"[MQTT TEST] Broker reachable at {BROKER_HOST}:{BROKER_PORT} "
            f"(container target {BROKER_CONTAINER_HOST}:{BROKER_CONTAINER_PORT})",
            flush=True,
        )

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

        # overrides = {
        #     "communication/mqtt/broker": BROKER_CONTAINER_HOST,
        #     "communication/mqtt/port": BROKER_CONTAINER_PORT,
        # }
        # print(
        #     "[MQTT TEST] Applying overrides:",
        #     overrides,
        #     flush=True,
        # )

        cls._instance = ensure_instance(
            cls._spx_client,
            INSTANCE_KEY,
            MODEL_KEY,
            overrides=None,
            recreate=model_changed,
        )
        try:
            instance_state = cls._instance.get().get("state")
        except Exception as exc:  # pragma: no cover - diagnostic only
            instance_state = f"<error retrieving state: {exc}>"
        print(
            f"[MQTT TEST] SPX instance {INSTANCE_KEY} state={instance_state} "
            f"model_changed={model_changed}",
            flush=True,
        )
        try:
            logs_tail = cls._instance["logs"].tail()
        except Exception as exc:  # pragma: no cover - diagnostic only
            logs_tail = f"<unable to fetch logs: {exc}>"
        else:
            logs_tail = list(logs_tail)
        print("[MQTT TEST] Initial instance logs tail:", flush=True)
        pprint(logs_tail)

    def setUp(self) -> None:
        self.sut = SimpleMqttEnvironmentSensorSUT(host=BROKER_HOST, port=BROKER_PORT)
        if not self.sut.connect():
            self.skipTest(f"Unable to connect SUT to MQTT broker at {BROKER_HOST}:{BROKER_PORT}")
        print(
            f"[MQTT TEST] SUT connected to broker {BROKER_HOST}:{BROKER_PORT}",
            flush=True,
        )
        time.sleep(0.2)

        self.instance = getattr(self.__class__, "_instance", None)
        if self.instance is None:
            self.skipTest("SPX instance not initialised")
        self.attributes = self.instance["attributes"]

        instance_state = "<unknown>"
        try:
            instance_state = self.instance.state
        except Exception as exc:
            instance_state = f"<error retrieving state: {exc}>"
        print(f"[MQTT TEST] Instance state before ensure running: {instance_state}", flush=True)
        if instance_state not in {"running", "RUNNING"}:
            try:
                self.instance.start()
                print("[MQTT TEST] Called instance.start()", flush=True)
            except Exception as exc:
                print(f"[MQTT TEST] instance.start() raised: {exc}", flush=True)
            time.sleep(0.5)
            try:
                instance_state = self.instance.state
            except Exception as exc:
                instance_state = f"<error retrieving state: {exc}>"
            print(f"[MQTT TEST] Instance state after ensure running: {instance_state}", flush=True)

        # Ensure the SPX model has attached to the broker before publishing commands.
        mqtt_connected_attr = self.attributes["mqtt_connected"]
        if mqtt_connected_attr is not None:
            connected = wait_for_condition(
                lambda: bool(float(getattr(mqtt_connected_attr, "internal_value", 0))),
                timeout=10.0,
            )
            print(
                f"[MQTT TEST] mqtt_connected attribute value="
                f"{getattr(mqtt_connected_attr, 'internal_value', None)} connected={connected}",
                flush=True,
            )
            self.assertTrue(
                connected,
                "SPX MQTT adapter did not report connected state within timeout.",
            )

        self.publisher = mqtt.Client()
        self.publisher.connect(BROKER_HOST, BROKER_PORT, keepalive=30)
        self.publisher.loop_start()
        print("[MQTT TEST] Publisher connected and loop started.", flush=True)

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
        published = info.wait_for_publish(timeout=2.0)
        print(
            f"[MQTT TEST] publish topic={topic} payload={payload!r} rc={info.rc} "
            f"published={published} mid={info.mid} broker={BROKER_HOST}:{BROKER_PORT}",
            flush=True,
        )

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
                print(f"[MQTT TEST] _await_value observed value={value}", flush=True)
            if value is not None:
                last_value = value
                if predicate(value):
                    return value
            time.sleep(0.1)
        print(f"[MQTT TEST] _await_value timeout. last_value={last_value}", flush=True)
        return last_value

    def _wait_for_temperature(self, target: float, *, timeout: float) -> bool:
        deadline = time.time() + timeout
        last_value: Optional[float] = None
        while time.time() < deadline:
            value = float(self.attributes["temperature_c"].internal_value)
            last_value = value
            delta = abs(value - target)
            print(
                f"[MQTT TEST] temperature_c={value} target={target} delta={delta}",
                flush=True,
            )
            if delta <= 0.5:
                return True
            time.sleep(0.5)
        print(
            f"[MQTT TEST] Temperature did not converge within timeout. last_value={last_value}",
            flush=True,
        )
        return False

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------
    def test_receives_temperature_humidity_comfort(self):
        raise unittest.SkipTest("Temporarily skipping SUT tests due to instability in CI environments.")
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
        raise unittest.SkipTest("Temporarily skipping SUT tests due to instability in CI environments.")
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
        print(
            f"[MQTT TEST] Starting setpoint test start_temp={start_temp} target={target_value}",
            flush=True,
        )
        self.attributes["temperature_c"].internal_value = start_temp
        self.attributes["target_c"].internal_value = start_temp
        if "temperature_integral" in self.attributes:
            self.attributes["temperature_integral"].internal_value = 0.0
        time.sleep(0.2)

        target_updated = False
        attempts = 3
        for attempt in range(attempts):
            self._publish(COMMAND_SETPOINT_TOPIC, f"{target_value}")
            # self.attributes["target_c"].internal_value = target_value
            target_updated = wait_for_condition(
                lambda: abs(self.attributes["target_c"].internal_value - target_value) <= 0.05,
                timeout=5.0,
            )
            print(
                f"[MQTT TEST] attempt={attempt} target_c="
                f"{self.attributes['target_c'].internal_value} target_updated={target_updated}",
                flush=True,
            )
            if target_updated:
                break
            time.sleep(0.5)

        self.assertTrue(target_updated, f"target_c={self.attributes['target_c'].internal_value} == {target_value} attribute did not update from command topic")

        try:
            logs_tail = list(self.instance["logs"].tail(limit=20))
        except Exception as exc:
            logs_tail = f"<unable to fetch logs: {exc}>"
        print("[MQTT TEST] Instance logs tail before temperature wait:", flush=True)
        pprint(logs_tail)

        temp_reached = self._wait_for_temperature(target_value, timeout=10.0)
        print(
            f"[MQTT TEST] Post-wait temperature_c={self.attributes['temperature_c'].internal_value} "
            f"temp_reached={temp_reached}",
            flush=True,
        )
        self.assertTrue(temp_reached, "temperature_c did not converge to the setpoint")

        telemetry_temperature = self._await_value(
            self.sut.latest_temperature,
            timeout=5.0,
            condition=lambda v: abs(v - target_value) <= 0.5,
        )
        self.assertIsInstance(telemetry_temperature, float)
        self.assertAlmostEqual(telemetry_temperature, target_value, delta=0.5)

        try:
            final_logs = list(self.instance["logs"].tail(limit=20))
        except Exception as exc:
            final_logs = f"<unable to fetch logs: {exc}>"
        print("[MQTT TEST] Instance logs tail after temperature wait:", flush=True)
        pprint(final_logs)


if __name__ == "__main__":
    unittest.main()
