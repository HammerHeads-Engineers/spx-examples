# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Hammerheads Engineers Sp. z o.o.
# See the accompanying LICENSE file for terms.

"""HTTP SUT helper that speaks to the ``open_meteo_static`` SPX model."""

from __future__ import annotations

import datetime as _dt
import os
from typing import Any, Dict, Iterable, Optional
from urllib.parse import quote

try:
    import requests
except Exception:  # pragma: no cover - optional dependency guard
    requests = None  # type: ignore[assignment]


class OpenMeteoStaticSUT:
    """Tiny client mirroring a weather app that consumes the simulated Open-Meteo API."""

    DEFAULT_BASE_URL = "http://127.0.0.1:8091"

    def __init__(
        self,
        base_url: Optional[str] = None,
        *,
        session: Optional["requests.Session"] = None,
        timeout: float = 5.0,
    ) -> None:
        if requests is None:  # pragma: no cover - dependency availability handled here
            raise RuntimeError(
                "requests is not available. Install requests to use the Open-Meteo SUT helper."
            )
        env_url = os.environ.get("OPEN_METEO_TEST_BASE_URL")
        resolved_base = base_url or env_url or self.DEFAULT_BASE_URL
        self.base_url = resolved_base.rstrip("/") or self.DEFAULT_BASE_URL
        self.timeout = timeout
        self._session = session or requests.Session()
        self._owns_session = session is None
        self._last_forecast: Optional[Dict[str, Any]] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def fetch_forecast(self, profile: str, horizon_hours: int) -> Dict[str, Any]:
        """Fetch the forecast payload for the given profile/horizon pair."""
        url = self._build_url(
            "/v1/forecast/{profile}/{horizon}",
            profile=profile,
            horizon=str(horizon_hours),
        )
        response = self._session.get(url, timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()
        self._last_forecast = payload
        return payload

    def set_profile(self, profile: str, horizon_hours: int) -> Dict[str, Any]:
        """Request the simulator to switch profiles and forecast horizon."""
        url = self._build_url("/simulator/profile")
        response = self._session.post(
            url,
            json={"profile": profile, "horizon_hours": horizon_hours},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def update_location(self, *, latitude: float, longitude: float, timezone: str) -> Dict[str, Any]:
        """Update the simulator location metadata."""
        url = self._build_url("/simulator/location")
        response = self._session.put(
            url,
            json={
                "latitude": latitude,
                "longitude": longitude,
                "timezone": timezone,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def last_forecast(self) -> Optional[Dict[str, Any]]:
        """Return the most recently cached forecast payload."""
        return self._last_forecast

    def should_irrigate(
        self,
        day: "_dt.date | _dt.datetime | str",
        *,
        forecast: Optional[Dict[str, Any]] = None,
        profile: Optional[str] = None,
        horizon_hours: Optional[int] = None,
        min_temp_c: float = 3.0,
        max_precip_probability: float = 40.0,
        max_daily_precip_mm: float = 3.0,
        min_dry_hours: int = 2,
    ) -> bool:
        """Decide whether irrigation should run on a specific day.

        The decision favours dry and warm windows by checking both daily aggregates and
        hourly precipitation probabilities. Either pass in a forecast payload explicitly
        or ensure ``fetch_forecast`` was called beforehand.
        """
        forecast_payload = forecast or self._last_forecast
        if forecast_payload is None:
            if profile is None or horizon_hours is None:
                raise ValueError(
                    "No forecast available. Either call fetch_forecast() first or "
                    "provide profile and horizon_hours so the helper can fetch one."
                )
            forecast_payload = self.fetch_forecast(profile, horizon_hours)

        day_key = _normalise_day_key(day)

        daily = forecast_payload.get("daily") or {}
        daily_times = list(daily.get("time") or [])
        if day_key not in daily_times:
            return False
        day_index = daily_times.index(day_key)

        precip_values = daily.get("precipitation_sum") or []
        daily_precip = _safe_index_float(precip_values, day_index, default=0.0)
        temp_max_values = daily.get("temperature_2m_max") or []
        max_temp = _safe_index_float(temp_max_values, day_index, default=min_temp_c - 1.0)

        if daily_precip > max_daily_precip_mm:
            return False
        if max_temp < min_temp_c:
            return False

        hourly = forecast_payload.get("hourly") or {}
        hourly_times = hourly.get("time") or []
        precip_probabilities = hourly.get("precipitation_probability") or []
        hourly_temps = hourly.get("temperature_2m") or []

        dry_hours = 0
        for timestamp, probability, temperature in zip(hourly_times, precip_probabilities, hourly_temps):
            if not isinstance(timestamp, str) or not timestamp.startswith(day_key):
                continue
            prob_value = _coerce_float(probability)
            temp_value = _coerce_float(temperature)
            if prob_value is None or temp_value is None:
                continue
            if prob_value <= max_precip_probability and temp_value >= min_temp_c:
                dry_hours += 1

        if dry_hours < min_dry_hours and precip_probabilities:
            return False

        return True

    def close(self) -> None:
        if not self._owns_session:
            return
        try:
            self._session.close()
        except Exception:  # pragma: no cover - defensive cleanup
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


def _normalise_day_key(value: "_dt.date | _dt.datetime | str") -> str:
    if isinstance(value, _dt.datetime):
        return value.date().isoformat()
    if isinstance(value, _dt.date):
        return value.isoformat()
    return str(value)


def _coerce_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_index_float(values: Iterable[Any], index: int, *, default: float) -> float:
    try:
        seq = values if isinstance(values, list) else list(values)
        raw = seq[index]
    except (IndexError, TypeError):
        return default
    coerced = _coerce_float(raw)
    if coerced is None:
        return default
    return coerced


__all__ = ["OpenMeteoStaticSUT"]
