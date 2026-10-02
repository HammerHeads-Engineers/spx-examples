"""Behavioral regressions found in the installed release model review."""
import ast
import math
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
CATALOG = yaml.safe_load((ROOT / "library/catalog/models.yaml").read_text(encoding="utf-8"))
MODELS = CATALOG["models"]
RELEASE_MODELS = [m for m in MODELS if set(m.get("protocols", [])) & {"modbus", "opcua", "knx", "bacnet"}]
BROKEN_IDS = {
    "Building.BMSController.OpcUa", "Building.LightingPanel.OpcUa",
    "Building.LightingZone.Knx", "Energy.EnergyMeter3Ph.Modbus",
    "Energy.EnergyMeterEatonPxm2000.Modbus", "Energy.EnergyMeterPm8000.Modbus",
    "Motion.VFDrive.Modbus", "Process.PIDController.Modbus",
    "Process.PackagingLine.OpcUa", "Process.Workcell.OpcUa",
}


def load(model):
    return yaml.safe_load((ROOT / model["path"]).read_text(encoding="utf-8"))


def initial_values(definition):
    return {k: v.get("default") if isinstance(v, dict) else v
            for k, v in definition["attributes"].items()}


def calculate(action, values):
    """Evaluate expressions with model attributes, without protocol services."""
    def substitute(match):
        path = match.group(1).lstrip(".")
        if path.startswith("attributes."):
            path = path[len("attributes."):]
        return repr(values[path])

    def expression(value, context):
        if not isinstance(value, str):
            return value
        source = re.sub(r"\$(?:in|out)\(([^)]+)\)", substitute, value)
        return eval(compile(ast.parse(source.strip(), mode="eval"), "<model>", "eval"), context)

    context = {"min": min, "max": max, "abs": abs, "int": int, "float": float,
               "round": round, "pow": pow, "math": math}
    context.update({k: v for k, v in action.items()
                    if k not in {"function", "call", "params", "name", "description"}})
    for key, value in action.get("params", {}).items():
        context[key] = expression(value, context)
    result = expression(action["call"], context)
    target = re.fullmatch(r"\$in\(([^)]+)\)", action["function"]).group(1).lstrip(".")
    values[target] = result
    return result


@pytest.mark.parametrize("model", [m for m in MODELS if m["id"] in BROKEN_IDS], ids=lambda m: m["id"])
def test_regression_actions_produce_typed_numeric_values(model):
    definition = load(model)
    values = initial_values(definition)
    values["__timer"] = 0.0
    for _ in range(5):
        values["__timer"] += 0.1
        for action in definition["actions"]:
            if "function" in action:
                calculate(action, values)
        for key, spec in definition["attributes"].items():
            if isinstance(spec, dict) and spec.get("type") in {"int", "float"}:
                assert isinstance(values[key], (int, float)), key
                assert math.isfinite(values[key]), key


@pytest.mark.parametrize("model", RELEASE_MODELS, ids=lambda m: m["id"])
def test_regular_scenarios_are_opt_in_and_overrides_match_types(model):
    definition = load(model)
    for name, scenario in definition.get("scenarios", {}).items():
        assert not scenario.get("enabled", False), name
        for path, value in scenario.get("overrides", {}).items():
            match = re.fullmatch(r"\$in\(([^)]+)\)", path)
            if match:
                spec = definition["attributes"].get(match.group(1).lstrip("."))
                if isinstance(spec, dict) and spec.get("type") == "str":
                    assert isinstance(value, str), (name, path, value)


def test_bms_maintenance_recovery_and_stable_zone_temperature():
    definition = load(next(m for m in MODELS if m["id"] == "Building.BMSController.OpcUa"))
    values = initial_values(definition)
    values["__timer"] = 0.0
    values.update(hvac_mode="off", fan_command_percent=0.0, pump_command_percent=0.0)
    for step in range(2000):
        if step == 100:
            values.update(hvac_mode="auto", fan_command_percent=55.0, pump_command_percent=60.0)
        values["__timer"] += 0.1
        for action in definition["actions"]:
            calculate(action, values)
    assert values["alarm_fan"] == 0
    assert values["fan_speed_percent"] == pytest.approx(55.0)
    assert 18.0 <= values["zone_temp_average_c"] <= 30.0
    assert 0.0 <= values["power_draw_kw"] <= values["demand_limit_kw"]


def test_bms_energy_tracks_elapsed_seconds():
    definition = load(next(m for m in MODELS if m["id"] == "Building.BMSController.OpcUa"))
    values = initial_values(definition)
    values["__timer"] = 0.0
    baseline = values["energy_consumption_kwh"]
    for t in [0.0, 0.1, 0.3, 0.9, 1.0]:
        values["__timer"] = t
        for action in definition["actions"]:
            calculate(action, values)
    assert values["energy_consumption_kwh"] - baseline == pytest.approx(78.0 / 3600.0)


def test_workcell_completion_updates_serial_and_quality_before_progress_reset():
    definition = load(next(m for m in MODELS if m["id"] == "Process.Workcell.OpcUa"))
    values = initial_values(definition)
    values.update(__timer=0.0, station_mode="auto", part_present=1, clamp_closed=1,
                  target_cycle_time_s=1.0)
    for i in range(100):
        values["__timer"] = i * 0.1
        for action in definition["actions"]:
            calculate(action, values)
    assert values["cycle_counter_total"] > 1
    assert values["latest_serial"] == "SN-{0:06d}".format(values["cycle_counter_total"])
    assert values["cycle_counter_ok"] > 0
    assert values["cycle_counter_nok"] > 0
    assert values["cycle_counter_ok"] + values["cycle_counter_nok"] == values["cycle_counter_total"]
    assert 119.0 < values["maintenance_timer_hours"] < 120.0


def test_lighting_power_and_daily_weekly_energy_use_the_same_units():
    definition = load(next(m for m in MODELS if m["id"] == "Building.LightingPanel.OpcUa"))
    values = initial_values(definition)
    values.update(__timer=0.0, zone1_target_percent=100.0, zone2_target_percent=100.0,
                  zone3_target_percent=100.0, zone1_level_percent=100.0,
                  zone2_level_percent=100.0, zone3_level_percent=100.0)
    baseline = values["energy_today_kwh"], values["energy_week_kwh"]
    for t in (0.0, 3600.0):
        values["__timer"] = t
        for action in definition["actions"]:
            calculate(action, values)
    assert values["lighting_power_kw"] == pytest.approx(3.0)
    assert values["energy_today_kwh"] - baseline[0] == pytest.approx(3.0)
    assert values["energy_week_kwh"] - baseline[1] == pytest.approx(3.0)
    values["panel_state"] = "off"
    baseline = values["energy_today_kwh"], values["energy_week_kwh"]
    values["__timer"] += 3600
    for action in definition["actions"]:
        calculate(action, values)
    assert values["lighting_power_kw"] == 0.0
    assert (values["energy_today_kwh"], values["energy_week_kwh"]) == baseline


def test_vfd_overload_scenario_reaches_alarm_and_disable_removes_torque():
    definition = load(next(m for m in MODELS if m["id"] == "Motion.VFDrive.Modbus"))
    values = initial_values(definition)
    values.update(__timer=0.0, speed_set_rpm=2200.0, torque_limit_percent=90.0)
    for step in range(300):
        values["__timer"] = step * 0.1
        for action in definition["actions"]:
            calculate(action, values)
    assert values["alarm_overload"] == 1
    values["enable"] = 0
    for action in definition["actions"]:
        calculate(action, values)
    assert values["torque_percent"] == 0.0
    assert values["alarm_overload"] == 0
