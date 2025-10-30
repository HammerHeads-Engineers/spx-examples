# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Hammerheads Engineers Sp. z o.o.
# See the accompanying LICENSE file for terms.

"""Minimal MQTT model registration example.

This script registers a tiny MQTT-backed device model, ensures an instance is
running, and provides helpful output for checking telemetry using an external
broker (e.g., eclipse-mosquitto).
"""

from __future__ import annotations

import os
from typing import Any, Dict

import spx_python

MODEL_KEY = "examples__mqtt_minimal"
INSTANCE_KEY = "mqtt_minimal_1"
BROKER_HOST = os.environ.get("MQTT_BROKER_HOST", "host.docker.internal")
BROKER_PORT = int(os.environ.get("MQTT_BROKER_PORT", "1883"))
PRODUCT_KEY = os.environ.get("SPX_PRODUCT_KEY")

if PRODUCT_KEY is None:
    raise ValueError("Environment variable SPX_PRODUCT_KEY is required.")

print(f"Connecting to SPX server at http://localhost:8000 with product key {PRODUCT_KEY!r}")
client = spx_python.init(address="http://localhost:8000", product_key=PRODUCT_KEY)


def _build_model_definition(broker_host: str, broker_port: int) -> Dict[str, Any]:
    return {
        # "name": "examples_mqtt_min_sensor",
        # "description": "Minimal MQTT environment sensor publishing telemetry and accepting a setpoint.",
        "attributes": {
            "temperature_c": 22.01,
            "target_c": 23.01,
            "humidity_percent": 45.0,
        },
        "communication": [
            {
                "mqtt": {
                    "broker": broker_host,
                    "port": broker_port,
                    "publish_interval": 0.5,
                    "topic_prefix": "spx/examples/min/env",
                    "default_qos": 1,
                    "default_retain": False,
                    "bindings": [
                        {
                            "attribute": "$ext(temperature_c)",
                            "topic": "telemetry/temperature_c",
                            "direction": "publish",
                        },
                        {
                            "attribute": "$ext(humidity_percent)",
                            "topic": "telemetry/humidity_percent",
                            "direction": "publish",
                        },
                        {
                            "attribute": "$ext(target_c)",
                            "topic": "telemetry/target_c",
                            "direction": "publish",
                        },
                        {
                            "attribute": "$attr(target_c)",
                            "topic": "setpoint_c",
                            "direction": "subscribe",
                        },
                    ],
                }
            }
        ],
    }


def ensure_model_registered() -> Dict[str, Any]:
    model_def = _build_model_definition(BROKER_HOST, BROKER_PORT)
    print(f"Registering model {MODEL_KEY!r} (MQTT broker: {BROKER_HOST}:{BROKER_PORT})")
    client["models"][MODEL_KEY] = model_def
    return model_def


def ensure_instance_running(model_key: str) -> None:
    instances = client["instances"]
    try:
        existing = instances[INSTANCE_KEY]
        print(f"Instance {INSTANCE_KEY!r} already exists; stopping and recreating to ensure fresh configuration.")
        try:
            existing.stop()
        except Exception:
            pass
        try:
            del instances[INSTANCE_KEY]
        except Exception:
            pass
    except Exception:
        pass

    print(f"Creating instance {INSTANCE_KEY!r} for model {model_key!r}")
    instances[INSTANCE_KEY] = model_key
    inst = instances[INSTANCE_KEY]

    print("Resetting and starting instance...")
    inst.reset()
    inst.start()
    print("Instance is running.")


def main() -> None:
    ensure_model_registered()
    ensure_instance_running(MODEL_KEY)

    print(
        "\nTelemetry tips:\n"
        f"  - Subscribe to 'spx/examples/min/env/#' using MQTT Explorer or mosquitto_sub.\n"
        "  - Publish a new setpoint (e.g. 26.5°C):\n"
        f"        mosquitto_pub -h {BROKER_HOST} -p {BROKER_PORT} "
        "-t spx/examples/min/env/setpoint_c -m 26.5\n"
        "  - Watch telemetry update every 0.5 s.\n"
    )


if __name__ == "__main__":
    main()
