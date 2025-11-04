# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Hammerheads Engineers Sp. z o.o.
# See the accompanying LICENSE file for terms.

"""Integration coverage for the AirQualityStaticSUT helper."""

from __future__ import annotations

import os
import pathlib
import unittest

from tests.common.spx_utils import bootstrap_model_instance, wait_for_condition
from tests.devices.air_quality_static_sut import AirQualityStaticSUT

try:
    import requests  # type: ignore
except Exception as exc:  # pragma: no cover - dependency guard mirrors SUT behaviour
    requests = None  # type: ignore[assignment]
    _REQUESTS_IMPORT_ERROR = exc
else:
    _REQUESTS_IMPORT_ERROR = None


ROOT = pathlib.Path(__file__).resolve().parents[1]
MODEL_PATH = ROOT / "library" / "iot" / "generic" / "air_quality_static.yaml"
MODEL_KEY = "tests__air_quality_static"
INSTANCE_KEY = "tests_air_quality_static_instance"

SPX_API_URL = os.environ.get("SPX_API_URL", "http://localhost:8000")
SPX_PRODUCT_KEY_ENV = "SPX_PRODUCT_KEY"

DEFAULT_PROFILE = "urban-baseline"
DEFAULT_TIMEOUT = float(os.environ.get("AIR_QUALITY_TEST_TIMEOUT", "5.0"))
SERVER_HOST = os.environ.get("AIR_QUALITY_TEST_HOST", "0.0.0.0")
SERVER_PORT = int(os.environ.get("AIR_QUALITY_TEST_PORT", "8092"))
BASE_URL = os.environ.get("AIR_QUALITY_TEST_BASE_URL", f"http://{SERVER_HOST}:{SERVER_PORT}")


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
class TestAirQualityStaticSUTIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import spx_python  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dependency guard
            raise unittest.SkipTest(f"spx_python not available: {exc}") from exc

        product_key = os.environ.get(SPX_PRODUCT_KEY_ENV)
        if not product_key:
            raise unittest.SkipTest(
                f"{SPX_PRODUCT_KEY_ENV} must be set to run Air Quality integration tests."
            )

        try:
            (
                cls._spx_client,
                cls._instance,
                cls._model_changed,
            ) = bootstrap_model_instance(
                spx_python,
                product_key=product_key,
                base_url=SPX_API_URL,
                model_path=MODEL_PATH,
                model_key=MODEL_KEY,
                instance_key=INSTANCE_KEY,
                attribute_overrides={
                    "communication/http_endpoint/port": SERVER_PORT,
                },
            )
        except Exception as exc:  # pragma: no cover - guarded skip for flaky environments
            raise unittest.SkipTest(f"Unable to bootstrap Air Quality model: {exc}") from exc

        attrs = cls._instance["attributes"]

        def _attr_value(name: str):
            value = attrs[name]
            if hasattr(value, "internal_value"):
                return value.internal_value
            return value

        cls._default_station_id = str(_attr_value("station_id"))
        cls._default_station_name = str(_attr_value("station_name"))
        cls._default_latitude = float(_attr_value("latitude"))
        cls._default_longitude = float(_attr_value("longitude"))
        cls._default_timezone = str(_attr_value("timezone"))
        cls._default_monitoring_window = int(_attr_value("monitoring_window_hours"))
        cls._default_measurement_interval = int(_attr_value("measurement_interval_minutes"))

        cls._default_current_timestamp = str(_attr_value("current_timestamp"))
        cls._default_current_pm2_5 = float(_attr_value("current_pm2_5"))
        cls._default_current_pm10 = float(_attr_value("current_pm10"))
        cls._default_current_no2 = float(_attr_value("current_no2"))
        cls._default_current_o3 = float(_attr_value("current_o3"))
        cls._default_current_aqi = float(_attr_value("current_aqi"))
        cls._default_current_aqi_category = str(_attr_value("current_aqi_category"))

        report_url = f"{BASE_URL}/v1/air-quality/{DEFAULT_PROFILE}"
        ready = wait_for_condition(lambda: _http_ready(report_url), timeout=15.0, interval=0.5)
        if not ready:
            raise unittest.SkipTest(
                f"Air Quality HTTP endpoint not reachable at {report_url}. "
                "Ensure the SPX instance is running and the port is forwarded."
            )

    def setUp(self) -> None:
        self.sut = AirQualityStaticSUT(base_url=BASE_URL, timeout=DEFAULT_TIMEOUT)
        self.addCleanup(self._cleanup_sut)

        # Reset simulator state before each test to guarantee determinism.
        self.sut.set_profile(DEFAULT_PROFILE, self._default_monitoring_window)
        self.sut.update_station(
            station_name=self._default_station_name,
            latitude=self._default_latitude,
            longitude=self._default_longitude,
            timezone=self._default_timezone,
        )
        self.sut.update_current(
            timestamp=self._default_current_timestamp,
            pm2_5=self._default_current_pm2_5,
            pm10=self._default_current_pm10,
            no2=self._default_current_no2,
            o3=self._default_current_o3,
            aqi=self._default_current_aqi,
            aqi_category=self._default_current_aqi_category,
        )

    def _cleanup_sut(self) -> None:
        if hasattr(self, "sut") and self.sut is not None:
            self.sut.close()

    def test_fetch_report_contains_station_metadata(self) -> None:
        report = self.sut.fetch_report(DEFAULT_PROFILE)

        station = report.get("station") or {}
        self.assertEqual(station.get("id"), self._default_station_id)
        self.assertEqual(station.get("name"), self._default_station_name)
        self.assertAlmostEqual(float(station.get("latitude", 0.0)), self._default_latitude, places=6)
        self.assertAlmostEqual(float(station.get("longitude", 0.0)), self._default_longitude, places=6)
        self.assertEqual(station.get("timezone"), self._default_timezone)

        self.assertEqual(report.get("profile"), DEFAULT_PROFILE)
        self.assertEqual(int(report.get("monitoring_window_hours", -1)), self._default_monitoring_window)
        self.assertEqual(int(report.get("measurement_interval_minutes", -1)), self._default_measurement_interval)
        self.assertIn("hourly_readings", report)
        self.assertIn("current", report)

    def test_set_profile_changes_active_profile(self) -> None:
        profile = "traffic-peak"
        window = 12

        response = self.sut.set_profile(profile, window)
        self.assertEqual(response.get("status"), "ok")
        self.assertEqual(response.get("active_profile"), profile)
        self.assertEqual(int(response.get("monitoring_window_hours", -1)), window)

        report = self.sut.fetch_report(profile)
        self.assertEqual(report.get("profile"), profile)
        self.assertEqual(int(report.get("monitoring_window_hours", -1)), window)

    def test_update_station_reflected_in_report(self) -> None:
        new_station_name = "Warsaw Test Station"
        new_lat = self._default_latitude + 0.15
        new_lon = self._default_longitude - 0.2
        new_tz = "Europe/Berlin"

        response = self.sut.update_station(
            station_name=new_station_name,
            latitude=new_lat,
            longitude=new_lon,
            timezone=new_tz,
        )
        self.assertEqual(response.get("status"), "ok")
        self.assertEqual(response.get("station_name"), new_station_name)
        self.assertAlmostEqual(float(response.get("latitude", 0.0)), new_lat, places=6)
        self.assertAlmostEqual(float(response.get("longitude", 0.0)), new_lon, places=6)
        self.assertEqual(response.get("timezone"), new_tz)

        report = self.sut.fetch_report(DEFAULT_PROFILE)
        station = report.get("station") or {}
        self.assertEqual(station.get("name"), new_station_name)
        self.assertAlmostEqual(float(station.get("latitude", 0.0)), new_lat, places=6)
        self.assertAlmostEqual(float(station.get("longitude", 0.0)), new_lon, places=6)
        self.assertEqual(station.get("timezone"), new_tz)

    def test_update_current_reflected_in_report(self) -> None:
        response = self.sut.update_current(
            timestamp="2025-01-01T18:00",
            pm2_5=38.4,
            pm10=62.0,
            no2=41.5,
            o3=47.3,
            aqi=93.0,
            aqi_category="unhealthy",
        )

        self.assertEqual(response.get("status"), "ok")
        self.assertEqual(response.get("aqi_category"), "unhealthy")

        report = self.sut.fetch_report(DEFAULT_PROFILE)
        current = report.get("current") or {}
        self.assertEqual(current.get("timestamp"), "2025-01-01T18:00")
        self.assertAlmostEqual(float(current.get("pm2_5", 0.0)), 38.4, places=3)
        self.assertAlmostEqual(float(current.get("pm10", 0.0)), 62.0, places=3)
        self.assertAlmostEqual(float(current.get("no2", 0.0)), 41.5, places=3)
        self.assertAlmostEqual(float(current.get("o3", 0.0)), 47.3, places=3)
        self.assertAlmostEqual(float(current.get("aqi", 0.0)), 93.0, places=3)
        self.assertEqual(current.get("aqi_category"), "unhealthy")

    def test_should_enable_purifier_flags_high_pollution(self) -> None:
        report = self.sut.fetch_report(DEFAULT_PROFILE)
        decision = self.sut.should_enable_purifier(
            report=report,
            pm2_5_limit=20.0,
            pm10_limit=35.0,
            aqi_limit=60.0,
        )
        self.assertTrue(decision)

    def test_should_enable_purifier_respects_thresholds(self) -> None:
        report = self.sut.fetch_report(DEFAULT_PROFILE)
        decision = self.sut.should_enable_purifier(
            report=report,
            pm2_5_limit=40.0,
            pm10_limit=70.0,
            aqi_limit=100.0,
        )
        self.assertFalse(decision)
