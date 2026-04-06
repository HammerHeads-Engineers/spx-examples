#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Subscribe to comfort index updates published by the MQTT environment sensor."""

from __future__ import annotations

import json
import os
import sys
from typing import Any

import paho.mqtt.client as mqtt

BROKER_HOST = os.environ.get("MQTT_BROKER_HOST", "localhost")
BROKER_PORT = int(os.environ.get("MQTT_BROKER_PORT", "1883"))
TOPIC = "spx/examples/env/telemetry/temperature_c"


def on_connect(client: mqtt.Client, userdata: Any, flags: dict, rc: int) -> None:
    if rc != 0:
        print(f"Failed to connect: rc={rc}", file=sys.stderr)
        return
    print(f"Connected to MQTT broker at {BROKER_HOST}:{BROKER_PORT}")
    client.subscribe(TOPIC)
    print(f"Subscribed to '{TOPIC}'")


def on_message(client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage) -> None:
    payload = msg.payload.decode("utf-8", errors="replace")
    try:
        value = json.loads(payload)
    except json.JSONDecodeError:
        value = payload
    print(f"comfort_index = {value}")


def main() -> int:
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(BROKER_HOST, BROKER_PORT, keepalive=30)
    except Exception as exc:
        print(f"Unable to connect to {BROKER_HOST}:{BROKER_PORT} -> {exc}", file=sys.stderr)
        return 1

    print("Waiting for comfort index messages... Ctrl+C to exit.")
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print("\nStopping subscriber...")
    finally:
        client.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
