# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Hammerheads Engineers Sp. z o.o.
# See the accompanying LICENSE file for terms.

"""BLE-style SUT helper for the vital signs monitor model."""

from __future__ import annotations

import asyncio
import os
from typing import Callable, Optional


class BleVitalSignsMonitorSUT:
    """Expose vital sign telemetry via a BLE-like interface.

    The helper can operate in two modes:
    * SPX mode (default) – talks directly to an SPX instance and mimics Bleak's API.
    * BLE mode – uses Bleak to connect to a real peripheral (requires BLE hardware).
    """

    SERVICE_UUID = "f0c0a100-8b3a-4e69-bdd0-9f0f613d1a90"
    BODY_TEMPERATURE_CHAR_UUID = "f0c0a101-8b3a-4e69-bdd0-9f0f613d1a90"
    SYSTOLIC_PRESSURE_CHAR_UUID = "f0c0a102-8b3a-4e69-bdd0-9f0f613d1a90"
    DIASTOLIC_PRESSURE_CHAR_UUID = "f0c0a103-8b3a-4e69-bdd0-9f0f613d1a90"
    HEART_RATE_CHAR_UUID = "f0c0a104-8b3a-4e69-bdd0-9f0f613d1a90"
    BLOOD_OXYGEN_CHAR_UUID = "f0c0a105-8b3a-4e69-bdd0-9f0f613d1a90"
    RESPIRATION_RATE_CHAR_UUID = "f0c0a106-8b3a-4e69-bdd0-9f0f613d1a90"
    BATTERY_LEVEL_CHAR_UUID = "f0c0a107-8b3a-4e69-bdd0-9f0f613d1a90"
    ACTIVITY_INTENSITY_CHAR_UUID = "f0c0a108-8b3a-4e69-bdd0-9f0f613d1a90"
    DEFAULT_DEVICE_NAME = "SpX Vital Signs Monitor"
    DEFAULT_INSTANCE_KEY = "ble_vital_signs_monitor"
    CHARACTERISTIC_ATTRIBUTE_MAP = {
        BODY_TEMPERATURE_CHAR_UUID: "bodyTemperatureC",
        SYSTOLIC_PRESSURE_CHAR_UUID: "systolicPressureMmHg",
        DIASTOLIC_PRESSURE_CHAR_UUID: "diastolicPressureMmHg",
        HEART_RATE_CHAR_UUID: "heartRateBpm",
        BLOOD_OXYGEN_CHAR_UUID: "bloodOxygenPercent",
        RESPIRATION_RATE_CHAR_UUID: "respirationRate",
        BATTERY_LEVEL_CHAR_UUID: "batteryLevelPercent",
        ACTIVITY_INTENSITY_CHAR_UUID: "activityIntensity",
    }

    def __init__(
        self,
        address: Optional[str] = None,
        *,
        device_name: Optional[str] = None,
        timeout: float = 5.0,
        scan_timeout: float = 5.0,
        client_factory: Optional[Callable[[], object]] = None,
        spx_client: Optional[object] = None,
        spx_instance: Optional[object] = None,
        spx_instance_key: Optional[str] = None,
        spx_base_url: Optional[str] = None,
        spx_product_key: Optional[str] = None,
    ) -> None:
        """
        Parameters
        ----------
        address:
            BLE address (or identifier) accepted by Bleak.
        timeout:
            Timeout (seconds) applied when establishing a connection.
        client_factory:
            Optional factory returning an `async with`-compatible client. Used mainly for testing.
        spx_client:
            Optional SPX client used when operating in SPX mode.
        spx_instance:
            Optional SPX instance object to reuse in SPX mode.
        spx_instance_key:
            Instance key to resolve in SPX mode (defaults to ``ble_vital_signs_monitor``).
        spx_base_url:
            Base URL used when instantiating an SPX client (defaults to ``SPX_API_URL`` env or localhost).
        spx_product_key:
            Product key used for SPX authentication (defaults to ``SPX_PRODUCT_KEY`` env).
        """
        self.address = address
        self.device_name = device_name or self.DEFAULT_DEVICE_NAME
        self.timeout = timeout
        self.scan_timeout = scan_timeout
        self._client_factory = client_factory
        self._resolved_device: Optional[object] = None
        self._spx_client = spx_client
        self._spx_instance = spx_instance
        self._spx_instance_key = spx_instance_key or self.DEFAULT_INSTANCE_KEY
        self._spx_base_url = spx_base_url or os.environ.get("SPX_API_URL", "http://localhost:8000")
        self._spx_product_key = spx_product_key or os.environ.get("SPX_PRODUCT_KEY")

        if client_factory is not None:
            self._backend = "custom"
        elif address or device_name:
            self._backend = "ble"
        else:
            self._backend = "spx"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def read_body_temperature(self) -> float:
        return self._read_float(self.BODY_TEMPERATURE_CHAR_UUID)

    def read_systolic_pressure(self) -> float:
        return self._read_float(self.SYSTOLIC_PRESSURE_CHAR_UUID)

    def read_diastolic_pressure(self) -> float:
        return self._read_float(self.DIASTOLIC_PRESSURE_CHAR_UUID)

    def read_heart_rate(self) -> float:
        return self._read_float(self.HEART_RATE_CHAR_UUID)

    def read_blood_oxygen(self) -> float:
        return self._read_float(self.BLOOD_OXYGEN_CHAR_UUID)

    def read_respiration_rate(self) -> float:
        return self._read_float(self.RESPIRATION_RATE_CHAR_UUID)

    def read_battery_level(self) -> float:
        return self._read_float(self.BATTERY_LEVEL_CHAR_UUID)

    def read_activity_intensity(self) -> float:
        """Connect to the device, read the activity intensity characteristic, and return it as float."""
        return self._read_float(self.ACTIVITY_INTENSITY_CHAR_UUID)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _read_float(self, char_uuid: str) -> float:
        raw = self._run(self._read_characteristic(char_uuid))
        return self._parse_utf8_float(raw)

    async def _read_characteristic(self, char_uuid: str) -> bytes:
        client = self._create_client()
        async with client:
            return await client.read_gatt_char(char_uuid)

    def _create_client(self):
        if self._client_factory is not None:
            return self._client_factory()

        if self._backend == "spx":
            self._ensure_spx_ready()
            return _SpxBleClient(
                instance=self._spx_instance,
                char_map=self.CHARACTERISTIC_ATTRIBUTE_MAP,
            )

        try:
            from bleak import BleakClient  # type: ignore
        except Exception as exc:  # pragma: no cover - dependency availability handled here
            raise RuntimeError(
                "bleak is not available. Install bleak to use the BLE SUT example."
            ) from exc

        self._ensure_device_resolved()
        target = self._resolved_device
        if target is None:
            raise RuntimeError("BLE device is not resolved. Provide an address or device name.")

        return BleakClient(target, timeout=self.timeout)

    def _ensure_spx_ready(self) -> None:
        if self._spx_instance is not None:
            return

        client = self._spx_client
        if client is None:
            if not self._spx_product_key:
                raise RuntimeError(
                    "SPX_PRODUCT_KEY must be set (or provided explicitly) to use the SPX backend."
                )
            try:
                import spx_python  # type: ignore
            except ImportError as exc:  # pragma: no cover - optional dependency guard
                raise RuntimeError(f"spx_python not available: {exc}") from exc
            client = spx_python.init(address=self._spx_base_url, product_key=self._spx_product_key)
            self._spx_client = client

        try:
            instance = client["instances"][self._spx_instance_key]
        except Exception as exc:
            raise RuntimeError(
                f"Unable to resolve SPX instance '{self._spx_instance_key}'. "
                "Ensure the model is registered and running."
            ) from exc

        self._spx_instance = instance

    def _ensure_device_resolved(self) -> None:
        if self._resolved_device is not None:
            return

        if self.address:
            self._resolved_device = self.address
            return

        if not self.device_name:
            raise RuntimeError("No device name configured for BLE discovery.")

        self._resolved_device = self._run(self._discover_device_by_name(self.device_name))

    async def _discover_device_by_name(self, target_name: str):
        try:
            from bleak import BleakScanner  # type: ignore
        except Exception as exc:
            raise RuntimeError(
                "bleak is not available. Install bleak to use the BLE SUT example."
            ) from exc

        devices = await BleakScanner.discover(timeout=self.scan_timeout)
        for device in devices:
            print("Discovered BLE device:", device)
            if getattr(device, "name", None) == target_name:
                return device

        raise RuntimeError(f"BLE device named {target_name!r} not found during discovery.")

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_utf8_float(payload: bytes) -> float:
        try:
            decoded = payload.decode("utf-8").strip()
        except Exception as exc:
            raise ValueError("Failed to decode BLE payload as UTF-8 text") from exc
        try:
            return float(decoded)
        except ValueError as exc:
            raise ValueError(f"BLE payload does not represent a float: {decoded!r}") from exc

    @staticmethod
    def _run(coro):
        """Execute coroutine in a fresh event loop to avoid clashing with user loops."""
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()


class _SpxBleClient:
    """Minimal async context manager mimicking BleakClient against an SPX instance."""

    def __init__(self, *, instance, char_map):
        self._instance = instance
        self._char_map = dict(char_map)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def read_gatt_char(self, char_uuid: str) -> bytes:
        attribute_name = self._char_map.get(char_uuid)
        if attribute_name is None:
            raise ValueError(f"Unsupported characteristic UUID: {char_uuid}")

        attributes = self._instance["attributes"]
        attribute = attributes[attribute_name]
        if attribute is None:
            raise RuntimeError(f"Attribute '{attribute_name}' not found on SPX instance.")

        value = getattr(attribute, "internal_value", None)
        if value is None:
            try:
                raw = attribute.get()
            except Exception:  # pragma: no cover - defensive
                raw = None
            if isinstance(raw, dict):
                value = raw.get("value", raw.get("state"))
            elif raw is not None:
                value = raw

        if value is None:
            raise RuntimeError(f"Attribute '{attribute_name}' has no readable value.")

        return str(value).encode("utf-8")


__all__ = ["BleVitalSignsMonitorSUT"]
