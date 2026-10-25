# SPDX-License-Identifier: MIT

import os
import unittest

import tests.shared.integration.mqtt_environment_sensor_sut_example as shared_mqtt

from tests.common.spx_utils import require_existing_instance


SPX_BASE_URL = os.environ.get("SPX_BASE_URL", "http://localhost:8000")
INSTANCE_KEY = "spx_env_sensor_mqtt"
MODEL_ID = "Env.EnvSensor.Mqtt"


class TestSimpleMqttEnvironmentSensorSUTIntegration(
    shared_mqtt.TestSimpleMqttEnvironmentSensorSUTIntegration
):
    """Run the shared MQTT env-sensor suite against the installer-created instance."""

    @classmethod
    def setUpClass(cls):
        if shared_mqtt.mqtt is None:
            raise unittest.SkipTest(
                "paho-mqtt is not installed; install it to run MQTT integration tests."
            )
        if not shared_mqtt._broker_available(shared_mqtt.BROKER_HOST, shared_mqtt.BROKER_PORT):
            raise unittest.SkipTest(
                f"MQTT broker not reachable at {shared_mqtt.BROKER_HOST}:{shared_mqtt.BROKER_PORT}"
            )

        try:
            import spx_python  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dependency guard
            raise unittest.SkipTest(f"spx_python not installed: {exc}") from exc

        product_key = os.environ.get("SPX_PRODUCT_KEY")
        if not product_key:
            raise unittest.SkipTest("SPX_PRODUCT_KEY must be set to run MQTT integration tests.")

        cls._spx_client = spx_python.init(address=SPX_BASE_URL, product_key=product_key)
        cls._instance = require_existing_instance(
            cls._spx_client,
            INSTANCE_KEY,
            expected_model_id=MODEL_ID,
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
