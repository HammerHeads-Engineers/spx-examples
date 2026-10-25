# SPDX-License-Identifier: MIT
# extensions/py_temp_sensor.py
import math
import time


class PyTempSensor:
    """
    Minimal sensor logic implemented in Python with a smooth setpoint response.
    - Keeps an internal temperature value `_t`
    - Exposes a property `temperature` used by SPX
    - The `temperature` setter updates a target setpoint `_sp` (no instant jump)
    - `tick()` moves the value toward the setpoint using first‑order inertia (time constant `tau`) and optional slew limit
    - Adds linear drift and a tiny sinusoidal ripple for realism
    - A rate limit (`max_slew`) is enabled by default
    - Large idle gaps are clamped by `dt_cap`
    """
    def __init__(self, start: float = 25.0, drift: float = 0.0, tau: float = 1.0, max_slew: float | None = 1.0, dt_cap: float = 0.2):
        # Current value and target setpoint
        self._t = float(start)
        self._sp = float(start)
        # Dynamics configuration
        self._drift = float(drift)           # units per second
        self._tau = float(tau) if tau is not None else 0.0  # time constant [s]
        self._max_slew = float(max_slew) if max_slew is not None else None  # max change per second
        self._dt_cap = float(dt_cap)
        # Time bookkeeping
        self._t0 = time.time()
        self._last = self._t0
        print(f"Initialized PyTempSensor with start={start}, drift={drift}, tau={self._tau}, max_slew={self._max_slew}")

    # Property used by SPX to read/write the attribute
    @property
    def temperature(self) -> float:
        print(f"Getting temperature: {self._t}")
        return self._t

    @temperature.setter
    def temperature(self, val: float):
        # Do not jump instantly; update the setpoint and let tick() glide toward it
        self._sp = float(val)
        self._last = time.time()
        print(f"Setpoint updated to: {self._sp}")

    @property
    def setpoint(self) -> float:
        return self._sp

    # Optional helper you can call from actions/logic
    def tick(self) -> float:
        now_abs = time.time()
        dt_raw = now_abs - self._last
        self._last = now_abs
        dt = max(0.0, min(dt_raw, getattr(self, "_dt_cap", 0.2)))

        # First-order lag toward setpoint (exponential easing)
        if self._tau > 0.0:
            alpha = 1.0 - math.exp(-dt / self._tau)
        else:
            alpha = 1.0

        step = (self._sp - self._t) * alpha

        # Optional max slew rate (units per second)
        if self._max_slew is not None:
            limit = self._max_slew * dt
            if step > 0:
                step = min(step, limit)
            else:
                step = max(step, -limit)

        # Move toward setpoint
        self._t += step

        # Add drift (per second) and a tiny ripple
        elapsed = now_abs - self._t0
        self._t += (self._drift * dt) + (0.05 * math.sin(elapsed))

        print(f"Tick: t={self._t:.3f} sp={self._sp:.3f} dt={dt:.3f} (raw={dt_raw:.3f}) alpha={alpha:.3f} step={step:.3f}")
        return self._t
