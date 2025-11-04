# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Hammerheads Engineers Sp. z o.o.
# See the accompanying LICENSE file for terms.

"""HTTP SUT helper talking to the ``air_quality_static`` SPX model."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional
from urllib.parse import quote

try:
    import requests
except Exception:  # pragma: no cover - dependency availability handled here
    requests = None  # type: ignore[assignment]


class AirQualityStaticSUT:
    """Small helper mirroring a client that consumes the static air-quality API."""

    DEFAULT_BASE_URL = "http://127.0.0.1:8092"

    def __init__(
        self,
        base_url: Optional[str] = None,
        *,
        session: Optional["requests.Session"] = None,
        timeout: float = 5.0,
    ) -> None:
        if requests is None:  # pragma: no cover - protect against missing dependency
            raise RuntimeError("requests is not available. Install requests to use the Air Quality SUT helper.")
        env_url = os.environ.get("AIR_QUALITY_TEST_BASE_URL")
        resolved_base = base_url or env_url or self.DEFAULT_BASE_URL
        self.base_url = resolved_base.rstrip("/") or self.DEFAULT_BASE_URL
        self.timeout = timeout
        self._session = session or requests.Session()
        self._owns_session = session is None
        self._last_report: Optional[Dict[str, Any]] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def fetch_report(self, profile: str) -> Dict[str, Any]:
        """Fetch the air-quality report for the requested profile."""
        url = self._build_url("/v1/air-quality/{profile}", profile=profile)
        response = self._session.get(url, timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()
        self._last_report = payload
        return payload

    def set_profile(self, profile: str, monitoring_window_hours: int) -> Dict[str, Any]:
        """Switch the simulator profile and monitoring window."""
        url = self._build_url("/simulator/profile")
        response = self._session.post(
            url,
            json={"profile": profile, "monitoring_window_hours": monitoring_window_hours},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def update_station(
        self,
        *,
        station_name: str,
        latitude: float,
        longitude: float,
        timezone: str,
    ) -> Dict[str, Any]:
        """Update station metadata exposed by the simulator."""
        url = self._build_url("/simulator/location")
        response = self._session.put(
            url,
            json={
                "station_name": station_name,
                "latitude": latitude,
                "longitude": longitude,
                "timezone": timezone,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def update_current(
        self,
        *,
        timestamp: str,
        pm2_5: float,
        pm10: float,
        no2: float,
        o3: float,
        aqi: float,
        aqi_category: str,
    ) -> Dict[str, Any]:
        """Update the instantaneous readings section of the simulator."""
        url = self._build_url("/simulator/current")
        response = self._session.patch(
            url,
            json={
                "timestamp": timestamp,
                "pm2_5": pm2_5,
                "pm10": pm10,
                "no2": no2,
                "o3": o3,
                "aqi": aqi,
                "aqi_category": aqi_category,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def last_report(self) -> Optional[Dict[str, Any]]:
        """Return the cached air-quality report if fetch_report has been called."""
        return self._last_report

    def should_enable_purifier(
        self,
        *,
        report: Optional[Dict[str, Any]] = None,
        profile: Optional[str] = None,
        pm2_5_limit: float = 25.0,
        pm10_limit: float = 45.0,
        aqi_limit: float = 70.0,
    ) -> bool:
        """Simple decision helper that recommends turning on filtration."""
        data = report or self._last_report
        if data is None:
            if profile is None:
                raise ValueError(
                    "No report available. Either call fetch_report() first or provide profile "
                    "so the helper can fetch a fresh report."
                )
            data = self.fetch_report(profile)

        current = data.get("current") or {}
        current_pm2_5 = _coerce_float(current.get("pm2_5"))
        current_pm10 = _coerce_float(current.get("pm10"))
        current_aqi = _coerce_float(current.get("aqi"))

        if current_pm2_5 is not None and current_pm2_5 >= pm2_5_limit:
            return True
        if current_pm10 is not None and current_pm10 >= pm10_limit:
            return True
        if current_aqi is not None and current_aqi >= aqi_limit:
            return True
        return False

    def close(self) -> None:
        if not self._owns_session:
            return
        try:
            self._session.close()
        except Exception:  # pragma: no cover - best effort cleanup
            pass

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _build_url(self, template: str, **params: str) -> str:
        path = template
        for key, value in params.items():
            placeholder = f"{{{key}}}"
            if placeholder in path:
                path = path.replace(placeholder, quote(value, safe=""))
        return f"{self.base_url}{path}"


def _coerce_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


__all__ = ["AirQualityStaticSUT"]
