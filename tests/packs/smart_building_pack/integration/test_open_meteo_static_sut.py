# SPDX-License-Identifier: MIT

import os
import unittest

import tests.shared.integration.open_meteo_static_sut as shared_om

from tests.common.spx_utils import require_existing_instance


SPX_BASE_URL = os.environ.get("SPX_BASE_URL", "http://localhost:8000")
INSTANCE_KEY = "spx_weather_feed"
MODEL_ID = "Weather.WeatherFeed.Http"


@unittest.skipIf(shared_om.requests is None, f"requests not installed: {shared_om._REQUESTS_IMPORT_ERROR}")
class TestOpenMeteoStaticSUTIntegration(shared_om.TestOpenMeteoStaticSUTIntegration):
    """Run the shared Open-Meteo suite against the installer-created instance."""

    @classmethod
    def setUpClass(cls):
        try:
            import spx_python  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dependency guard
            raise unittest.SkipTest(f"spx_python not available: {exc}") from exc

        product_key = os.environ.get(shared_om.SPX_PRODUCT_KEY_ENV)
        if not product_key:
            raise unittest.SkipTest(
                f"{shared_om.SPX_PRODUCT_KEY_ENV} must be set to run Open-Meteo integration tests."
            )

        cls._spx_client = spx_python.init(address=SPX_BASE_URL, product_key=product_key)
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

        attrs = cls._instance["attributes"]

        def _attr_value(name: str):
            value = attrs[name]
            if hasattr(value, "internal_value"):
                return value.internal_value
            return value

        cls._default_latitude = float(_attr_value("k__latitude"))
        cls._default_longitude = float(_attr_value("k__longitude"))
        cls._default_timezone = str(_attr_value("k__timezone"))

        forecast_url = f"{shared_om.BASE_URL}/v1/forecast/{shared_om.DEFAULT_PROFILE}/{shared_om.DEFAULT_HORIZON}"
        ready = shared_om.wait_for_condition(
            lambda: shared_om._http_ready(forecast_url), timeout=15.0, interval=0.5
        )
        if not ready:
            raise unittest.SkipTest(
                f"Open-Meteo HTTP endpoint not reachable at {forecast_url}. "
                "Ensure the SPX instance is running and the port is forwarded."
            )
