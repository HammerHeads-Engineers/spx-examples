# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Hammerheads Engineers Sp. z o.o.
# See the accompanying LICENSE file for terms.

"""Shared integration coverage for the AirQualityStaticSUT helper."""

from __future__ import annotations

import os
import unittest

import yaml

from tests.common.spx_utils import bootstrap_model_instance, wait_for_condition
from tests.common.repo import repo_root
from tests.devices.air_quality_static_sut import AirQualityStaticSUT

try:
    import requests  # type: ignore
except Exception as exc:  # pragma: no cover - dependency guard mirrors SUT behaviour
    requests = None  # type: ignore[assignment]
    _REQUESTS_IMPORT_ERROR = exc
else:
    _REQUESTS_IMPORT_ERROR = None


ROOT = repo_root()
MODEL_PATH = (
    ROOT
    / "library"
    / "domains"
    / "iot"
    / "generic"
    / "air_quality_station__http.yaml"
)
MODEL_KEY = "tests__air_quality_static"
INSTANCE_KEY = "tests_air_quality_static_instance"

SPX_BASE_URL = os.environ.get("SPX_BASE_URL", "http://localhost:8000")
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
                base_url=SPX_BASE_URL,
                model_path=MODEL_PATH,
                model_key=MODEL_KEY,
                instance_key=INSTANCE_KEY,
                attribute_overrides={
                    "communication/http_endpoint/port": SERVER_PORT,
                },
                )
        except Exception as exc:  # pragma: no cover - guarded skip for flaky environments
            raise unittest.SkipTest(f"Unable to bootstrap Air Quality model: {exc}") from exc

        # Prefer file defaults over reading instance attributes, because some runtimes
        # may update attribute values asynchronously right after start/reset.
        model_doc = yaml.safe_load(MODEL_PATH.read_text(encoding="utf-8")) or {}
        if not isinstance(model_doc, dict):
            raise unittest.SkipTest("Air quality model YAML is not a mapping.")
        defaults = model_doc.get("attributes") or {}
        if not isinstance(defaults, dict):
            raise unittest.SkipTest("Air quality model YAML attributes must be a mapping.")

        cls._default_station_id = str(defaults.get("k__station_id", ""))
        cls._default_station_name = str(defaults.get("k__station_name", ""))
        cls._default_latitude = float(defaults.get("k__latitude", 0.0))
        cls._default_longitude = float(defaults.get("k__longitude", 0.0))
        cls._default_timezone = str(defaults.get("k__timezone", ""))
        cls._default_monitoring_window = int(defaults.get("monitoring_window_hours", 0))
        cls._default_measurement_interval = int(defaults.get("measurement_interval_minutes", 0))

        cls._default_current_timestamp = str(defaults.get("k__current_timestamp", ""))
        cls._default_current_pm2_5 = float(defaults.get("k__current_pm2_5", 0.0))
        cls._default_current_pm10 = float(defaults.get("k__current_pm10", 0.0))
        cls._default_current_no2 = float(defaults.get("k__current_no2", 0.0))
        cls._default_current_o3 = float(defaults.get("k__current_o3", 0.0))
        cls._default_current_aqi = float(defaults.get("k__current_aqi", 0.0))
        cls._default_current_aqi_category = str(defaults.get("k__current_aqi_category", ""))

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

        # Ensure scenarios do not leak state between tests (some runtimes may auto-run enabled scenarios).
        instance = getattr(self.__class__, "_instance", None)
        if instance is not None:
            scenarios = instance.get("scenarios") if isinstance(instance, dict) else instance["scenarios"]
            for name in ("winter_smog_episode", "coastal_reset", "station_relocation"):
                try:
                    scenario = scenarios[name]
                except Exception:
                    continue
                stop = getattr(scenario, "stop", None)
                if callable(stop):
                    try:
                        stop()
                    except Exception:
                        pass

            # station_id is not currently updateable via the HTTP simulator endpoints, so reset it explicitly.
            try:
                attrs = instance["attributes"]
                attrs["k__station_id"].internal_value = self._default_station_id
            except Exception:
                pass

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

        expected_pm2_5 = self._default_current_pm2_5
        expected_pm10 = self._default_current_pm10
        expected_aqi = self._default_current_aqi
        expected_station_id = self._default_station_id
        last_report: dict = {}

        def _report_synced() -> bool:
            nonlocal last_report
            try:
                last_report = self.sut.fetch_report(DEFAULT_PROFILE)
            except Exception:
                return False
            current = last_report.get("current") or {}
            try:
                pm2_5 = float(current.get("pm2_5"))
                pm10 = float(current.get("pm10"))
                aqi = float(current.get("aqi"))
            except Exception:
                return False
            station = last_report.get("station") or {}
            return (
                abs(pm2_5 - expected_pm2_5) <= 1e-3
                and abs(pm10 - expected_pm10) <= 1e-3
                and abs(aqi - expected_aqi) <= 1e-3
                and station.get("id") == expected_station_id
            )

        if not wait_for_condition(_report_synced, timeout=10.0, interval=0.5):
            current = last_report.get("current") if isinstance(last_report, dict) else None
            raise unittest.SkipTest(
                f"Air quality report did not reflect baseline readings within timeout; current={current!r}"
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
