# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Hammerheads Engineers Sp. z o.o.
# See the accompanying LICENSE file for terms.

"""Shared integration coverage for the OpenMeteoStaticSUT helper."""

from __future__ import annotations

import os
from pprint import pprint
import unittest
from tests.common.spx_utils import bootstrap_model_instance, wait_for_condition
from tests.common.repo import repo_root
from tests.devices.open_meteo_static_sut import OpenMeteoStaticSUT

try:
    import requests  # type: ignore
except Exception as exc:  # pragma: no cover - dependency guard mirrors SUT behaviour
    requests = None  # type: ignore[assignment]
    _REQUESTS_IMPORT_ERROR = exc
else:
    _REQUESTS_IMPORT_ERROR = None


ROOT = repo_root()
MODEL_PATH = ROOT / "library" / "domains" / "weather" / "weather_forecast__http.yaml"
MODEL_KEY = "tests__open_meteo_static"
INSTANCE_KEY = "tests_open_meteo_static_instance"

SPX_BASE_URL = os.environ.get("SPX_BASE_URL", "http://localhost:8000")
SPX_PRODUCT_KEY_ENV = "SPX_PRODUCT_KEY"

DEFAULT_PROFILE = "clear"
DEFAULT_HORIZON = 48
DEFAULT_TIMEOUT = float(os.environ.get("OPEN_METEO_TEST_TIMEOUT", "5.0"))
SERVER_HOST = os.environ.get("OPEN_METEO_TEST_HOST", "0.0.0.0")
SERVER_PORT = int(os.environ.get("OPEN_METEO_TEST_PORT", "8091"))
BASE_URL = os.environ.get("OPEN_METEO_TEST_BASE_URL", f"http://{SERVER_HOST}:{SERVER_PORT}")


def _http_ready(url: str) -> bool:
    if requests is None:
        return False
    try:
        response = requests.get(url, timeout=1.5)
        response.raise_for_status()
    except Exception:
        return False
    return True


@unittest.skipIf(requests is None, f"requests not installed: {_REQUESTS_IMPORT_ERROR}")
class TestOpenMeteoStaticSUTIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import spx_python  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dependency guard
            raise unittest.SkipTest(f"spx_python not available: {exc}") from exc

        product_key = os.environ.get(SPX_PRODUCT_KEY_ENV)
        if not product_key:
            raise unittest.SkipTest(f"{SPX_PRODUCT_KEY_ENV} must be set to run Open-Meteo integration tests.")

        try:
            (
                cls._spx_client,
                cls._instance,
                cls._model_changed,
            ) = bootstrap_model_instance(
                spx_python,
                product_key=product_key,
                base_url=SPX_BASE_URL,
                model_path=MODEL_PATH,
                model_key=MODEL_KEY,
                instance_key=INSTANCE_KEY,
                attribute_overrides={
                    "communication/http_endpoint/port": SERVER_PORT,
                },
            )
        except Exception as exc:  # pragma: no cover - guarded skip for flaky environments
            raise unittest.SkipTest(f"Unable to bootstrap Open-Meteo model: {exc}") from exc

        attrs = cls._instance["attributes"]

        def _attr_value(name: str):
            value = attrs[name]
            if hasattr(value, "internal_value"):
                return value.internal_value
            return value

        cls._default_latitude = float(_attr_value("k__latitude"))
        cls._default_longitude = float(_attr_value("k__longitude"))
        cls._default_timezone = str(_attr_value("k__timezone"))

        forecast_url = f"{BASE_URL}/v1/forecast/{DEFAULT_PROFILE}/{DEFAULT_HORIZON}"
        ready = wait_for_condition(lambda: _http_ready(forecast_url), timeout=15.0, interval=0.5)
        if not ready:
            raise unittest.SkipTest(
                f"Open-Meteo HTTP endpoint not reachable at {forecast_url}. "
                "Ensure the SPX instance is running and the port is forwarded."
            )

    def setUp(self) -> None:
        self.sut = OpenMeteoStaticSUT(base_url=BASE_URL, timeout=DEFAULT_TIMEOUT)
        self.addCleanup(self._cleanup_sut)
        # Reset simulator state before each test to guarantee determinism.
        self.sut.set_profile(DEFAULT_PROFILE, DEFAULT_HORIZON)
        self.sut.update_location(
            latitude=self._default_latitude,
            longitude=self._default_longitude,
            timezone=self._default_timezone,
        )

    def _cleanup_sut(self) -> None:
        if hasattr(self, "sut") and self.sut is not None:
            self.sut.close()

    def test_fetch_clear_profile_forecast(self) -> None:
        forecast = self.sut.fetch_forecast(DEFAULT_PROFILE, DEFAULT_HORIZON)

        self.assertEqual(forecast.get("forecast_profile"), DEFAULT_PROFILE)
        self.assertEqual(int(forecast.get("forecast_horizon_hours", -1)), DEFAULT_HORIZON)
        self.assertAlmostEqual(float(forecast["latitude"]), self._default_latitude, places=3)
        self.assertAlmostEqual(float(forecast["longitude"]), self._default_longitude, places=3)
        self.assertEqual(forecast.get("timezone"), self._default_timezone)
        self.assertIn("hourly", forecast)
        self.assertIn("daily", forecast)
        self.assertIn("current_weather", forecast)

    def test_set_profile_changes_active_profile(self) -> None:
        profile = "storm-front"
        horizon = 24

        response = self.sut.set_profile(profile, horizon)
        self.assertEqual(response.get("status"), "ok")
        self.assertEqual(response.get("active_profile"), profile)
        self.assertEqual(int(response.get("forecast_horizon_hours", -1)), horizon)

        forecast = self.sut.fetch_forecast(profile, horizon)
        self.assertEqual(forecast.get("forecast_profile"), profile)
        self.assertEqual(int(forecast.get("forecast_horizon_hours", -1)), horizon)

    def test_update_location_reflected_in_forecast(self) -> None:
        new_lat = self._default_latitude + 0.25
        new_lon = self._default_longitude - 0.4
        new_tz = "Europe/Berlin"

        response = self.sut.update_location(latitude=new_lat, longitude=new_lon, timezone=new_tz)
        self.assertEqual(response.get("status"), "ok")
        self.assertAlmostEqual(float(response.get("latitude", 0.0)), new_lat, places=6)
        self.assertAlmostEqual(float(response.get("longitude", 0.0)), new_lon, places=6)
        self.assertEqual(response.get("timezone"), new_tz)

        forecast = self.sut.fetch_forecast(DEFAULT_PROFILE, DEFAULT_HORIZON)
        self.assertAlmostEqual(float(forecast.get("latitude", 0.0)), new_lat, places=6)
        self.assertAlmostEqual(float(forecast.get("longitude", 0.0)), new_lon, places=6)
        self.assertEqual(forecast.get("timezone"), new_tz)

    def test_should_irrigate_detects_suitable_window(self) -> None:
        forecast = self.sut.fetch_forecast(DEFAULT_PROFILE, DEFAULT_HORIZON)
        decision = self.sut.should_irrigate(
            "2025-01-01",
            forecast=forecast,
            min_temp_c=2.5,
            max_precip_probability=35.0,
            max_daily_precip_mm=3.0,
            min_dry_hours=2,
        )
        self.assertTrue(decision)

    def test_should_irrigate_rejects_when_risk_too_high(self) -> None:
        forecast = self.sut.fetch_forecast(DEFAULT_PROFILE, DEFAULT_HORIZON)
        pprint(forecast)
        decision = self.sut.should_irrigate(
            "2025-01-01",
            forecast=forecast,
            min_temp_c=6.0,
            max_precip_probability=15.0,
            max_daily_precip_mm=2.0,
            min_dry_hours=4,
        )
        self.assertFalse(decision)
