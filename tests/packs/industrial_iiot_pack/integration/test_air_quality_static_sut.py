# SPDX-License-Identifier: MIT

import os
import unittest

import yaml

import tests.shared.integration.air_quality_static_sut as shared_aq

from tests.common.spx_utils import require_existing_instance


SPX_API_URL = os.environ.get("SPX_API_URL", "http://localhost:8000")
INSTANCE_KEY = "spx_air_quality_feed"
MODEL_ID = "Env.AirQualityStation.Http"


@unittest.skipIf(shared_aq.requests is None, f"requests not installed: {shared_aq._REQUESTS_IMPORT_ERROR}")
class TestAirQualityStaticSUTIntegration(shared_aq.TestAirQualityStaticSUTIntegration):
    """Run the shared air-quality suite against the installer-created instance."""

    @classmethod
    def setUpClass(cls):
        try:
            import spx_python  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dependency guard
            raise unittest.SkipTest(f"spx_python not available: {exc}") from exc

        product_key = os.environ.get(shared_aq.SPX_PRODUCT_KEY_ENV)
        if not product_key:
            raise unittest.SkipTest(
                f"{shared_aq.SPX_PRODUCT_KEY_ENV} must be set to run Air Quality integration tests."
            )

        cls._spx_client = spx_python.init(address=SPX_API_URL, product_key=product_key)
        cls._instance = require_existing_instance(
            cls._spx_client,
            INSTANCE_KEY,
            expected_model_id=MODEL_ID,
            ensure_running=False,
        )
        cls._model_changed = False

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

        model_doc = yaml.safe_load(shared_aq.MODEL_PATH.read_text(encoding="utf-8")) or {}
        if not isinstance(model_doc, dict):
            raise unittest.SkipTest("Air quality model YAML is not a mapping.")
        defaults = model_doc.get("attributes") or {}
        if not isinstance(defaults, dict):
            raise unittest.SkipTest("Air quality model YAML attributes must be a mapping.")

        cls._default_station_id = str(defaults.get("station_id", ""))
        cls._default_station_name = str(defaults.get("station_name", ""))
        cls._default_latitude = float(defaults.get("latitude", 0.0))
        cls._default_longitude = float(defaults.get("longitude", 0.0))
        cls._default_timezone = str(defaults.get("timezone", ""))
        cls._default_monitoring_window = int(defaults.get("monitoring_window_hours", 0))
        cls._default_measurement_interval = int(defaults.get("measurement_interval_minutes", 0))

        cls._default_current_timestamp = str(defaults.get("current_timestamp", ""))
        cls._default_current_pm2_5 = float(defaults.get("current_pm2_5", 0.0))
        cls._default_current_pm10 = float(defaults.get("current_pm10", 0.0))
        cls._default_current_no2 = float(defaults.get("current_no2", 0.0))
        cls._default_current_o3 = float(defaults.get("current_o3", 0.0))
        cls._default_current_aqi = float(defaults.get("current_aqi", 0.0))
        cls._default_current_aqi_category = str(defaults.get("current_aqi_category", ""))

        report_url = f"{shared_aq.BASE_URL}/v1/air-quality/{shared_aq.DEFAULT_PROFILE}"
        ready = shared_aq.wait_for_condition(
            lambda: shared_aq._http_ready(report_url), timeout=15.0, interval=0.5
        )
        if not ready:
            raise unittest.SkipTest(
                f"Air Quality HTTP endpoint not reachable at {report_url}. "
                "Ensure the SPX instance is running and the port is forwarded."
            )
