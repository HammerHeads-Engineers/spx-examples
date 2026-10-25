# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Hammerheads Engineers Sp. z o.o.
# See the accompanying LICENSE file for terms.

"""Minimal MQTT SUT helper for the environment sensor example."""

from __future__ import annotations

import threading
from typing import Dict, Optional


class SimpleMqttEnvironmentSensorSUT:
    """Tiny helper that subscribes to core telemetry topics and exposes last values."""

    TOPIC_PREFIX = "spx/examples/env/telemetry"
    TEMPERATURE_TOPIC = f"{TOPIC_PREFIX}/temperature_c"
    HUMIDITY_TOPIC = f"{TOPIC_PREFIX}/humidity_percent"
    COMFORT_TOPIC = f"{TOPIC_PREFIX}/comfort_index"

    SUBSCRIBE_TOPICS = (
        TEMPERATURE_TOPIC,
        HUMIDITY_TOPIC,
        COMFORT_TOPIC,
    )

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 1883,
    ) -> None:
        self.host = host
        self.port = port
        self._client: Optional[object] = None
        self._lock = threading.Lock()
        self._values: Dict[str, float] = {}

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------
    def connect(self) -> bool:
        if self._client is not None:
            return True
        client = self._create_client()
        try:
            client.connect(self.host, self.port, keepalive=30)
        except Exception:
            return False

        client.loop_start()
        for topic in self.SUBSCRIBE_TOPICS:
            client.subscribe(topic)
        self._client = client
        return True

    def close(self) -> None:
        client = self._client
        self._client = None
        if client is None:
            return
        try:
            client.loop_stop()
        except Exception:
            pass
        try:
            client.disconnect()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Telemetry getters
    # ------------------------------------------------------------------
    def latest_temperature(self) -> Optional[float]:
        return self._values.get(self.TEMPERATURE_TOPIC)

    def latest_humidity(self) -> Optional[float]:
        return self._values.get(self.HUMIDITY_TOPIC)

    def latest_comfort_index(self) -> Optional[float]:
        return self._values.get(self.COMFORT_TOPIC)

    # ------------------------------------------------------------------
    # Internal plumbing
    # ------------------------------------------------------------------
    def _create_client(self):
        try:
            from paho.mqtt import client as mqtt_client  # type: ignore
        except Exception as exc:  # pragma: no cover - dependency missing handled here
            raise RuntimeError(
                "paho-mqtt is not available. Install paho-mqtt to use the MQTT SUT example."
            ) from exc

        client = mqtt_client.Client()
        client.on_connect = self._on_connect
        client.on_message = self._on_message
        return client

    def _on_connect(self, client, userdata, flags, rc):  # pragma: no cover - trivial flag update
        if rc != 0:
            return
        for topic in self.SUBSCRIBE_TOPICS:
            client.subscribe(topic)

    def _on_message(self, client, userdata, message) -> None:  # pragma: no cover - trivial callback
        try:
            payload = message.payload.decode("utf-8").strip()
        except Exception:
            return

        value = self._coerce_float(payload)
        if value is None:
            return

        topic = getattr(message, "topic", "")
        if topic not in self.SUBSCRIBE_TOPICS:
            return

        with self._lock:
            self._values[topic] = value

    @staticmethod
    def _coerce_float(payload: str) -> Optional[float]:
        try:
            return float(payload)
        except (TypeError, ValueError):
            return None


__all__ = ["SimpleMqttEnvironmentSensorSUT"]
