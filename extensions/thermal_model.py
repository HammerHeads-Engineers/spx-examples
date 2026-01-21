# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Hammerheads Engineers Sp. z o.o.
# Helper routines for thermal simulations and actuator dynamics.
import math
from typing import Tuple

import numpy as np


def first_order_step(current: float, target: float, dt: float, tau: float, limit: Tuple[float, float] = (0.0, 100.0)) -> float:
    """
    First-order lag toward the target with an exponential response.
    - current: present value
    - target: desired value
    - dt: time step
    - tau: time constant (<=0 means no lag)
    - limit: clamp range for the result
    """
    if tau <= 0:
        next_val = target
    else:
        alpha = 1.0 - math.exp(-dt / max(tau, 1e-6))
        next_val = current + (target - current) * alpha
    lo, hi = limit
    return float(np.clip(next_val, lo, hi))


def thermal_step(
    temp: float,
    ambient: float,
    power: float,
    heat_coeff: float,
    cool_coeff: float,
    dt: float,
    mass: float = 1.0,
    limit: Tuple[float, float] | None = None,
) -> float:
    """
    Single-step update for a linear thermal system with heating and cooling:
      dT/dt = (heat_coeff * power - cool_coeff * (T - ambient)) / mass
    Uses the closed-form solution for constant power over dt.
    """
    mass_eff = max(mass, 1e-6)
    cool_rate = cool_coeff / mass_eff
    heat_rate = (heat_coeff * power) / mass_eff

    if cool_coeff > 0:
        decay = math.exp(-cool_rate * dt)
        steady = ambient + heat_rate / max(cool_rate, 1e-6)
        next_temp = steady + (temp - steady) * decay
    else:
        # No cooling → simple forward Euler on heating
        next_temp = temp + heat_rate * dt

    if limit is not None:
        lo, hi = limit
        next_temp = float(np.clip(next_temp, lo, hi))
    return float(next_temp)
