"""Read finite OCPP meter samples without replacing valid telemetry on errors."""

from math import isfinite


def meter_reading(frames, measurand, previous):
    """Return the latest valid energy (Wh) or power (W) sample."""
    units = {"Energy.Active.Import.Register": {"Wh": 1.0, "kWh": 1000.0},
             "Power.Active.Import": {"W": 1.0, "kW": 1000.0}}
    accepted = units.get(measurand, {})
    default_unit = "Wh" if measurand.startswith("Energy.") else "W"
    result = previous
    for frame in frames if isinstance(frames, list) else []:
        if not isinstance(frame, dict):
            continue
        samples = frame.get("sampledValue", frame.get("sampled_value", []))
        for sample in samples if isinstance(samples, list) else []:
            if not isinstance(sample, dict):
                continue
            if sample.get("measurand", "Energy.Active.Import.Register") != measurand:
                continue
            factor = accepted.get(sample.get("unit", default_unit))
            if factor is None or isinstance(sample.get("value"), bool):
                continue
            try:
                value = float(sample["value"]) * factor
            except (KeyError, TypeError, ValueError, OverflowError):
                continue
            if isfinite(value):
                result = value
    return result
