"""Regressions from rc.86: elapsed time, opt-in demos and automatic docking."""
import math

import pytest

from tests.core.unit.test_release_model_behavior import MODELS, calculate, initial_values, load

MQTT_IDS = {
    "Energy.EnergyMeter3Ph.Mqtt", "IIoT.LineCounter.Mqtt", "Logistics.AGVVehicle.Mqtt",
    "Building.RobotVacuum.Mqtt", "Condition.ConditionMonitor.Mqtt", "Env.EnvSensor.Mqtt",
}
MQTT_MODELS = [m for m in MODELS if m["id"] in MQTT_IDS]


def model(model_id):
    definition = load(next(m for m in MODELS if m["id"] == model_id))
    values = initial_values(definition)
    values["__timer"] = 0.0
    return definition, values


def tick(definition, values, time):
    values["__timer"] = time
    for action in definition["actions"]:
        if "function" in action:
            calculate(action, values)


@pytest.mark.parametrize("entry", MQTT_MODELS, ids=lambda m: m["id"])
def test_mqtt_family_starts_without_conflicting_demo_scenarios(entry):
    definition = load(entry)
    for name, scenario in definition.get("scenarios", {}).items():
        assert not scenario.get("enabled", False), name
    values = initial_values(definition)
    for time in (0.0, 0.1, 0.3, 0.9, 1.0):
        tick(definition, values, time)
    for name, value in values.items():
        if isinstance(value, (int, float)):
            assert math.isfinite(value), name


@pytest.mark.parametrize("entry", MQTT_MODELS, ids=lambda m: m["id"])
def test_mqtt_family_uses_the_bundled_broker_with_overridable_endpoints(entry):
    definition = load(entry)
    specs = definition["meta_parameters"]
    assert specs["mqtt_broker_host"]["default"] == "mosquitto-server"
    for block in definition["communication"]:
        if "mqtt" in block:
            assert block["mqtt"]["broker"] == "$param(mqtt_broker_host)"
            assert block["mqtt"]["port"] == "$param(mqtt_broker_port)"
            assert block["mqtt"]["topic_prefix"] == "$param(mqtt_topic_prefix)"


@pytest.mark.parametrize("times", [(0., 1., 2., 10.), (0., .1, .2, .7, 1., 1., 10.)])
@pytest.mark.parametrize("model_id,output,expected", [
    ("Energy.EnergyMeter3Ph.Mqtt", "energy_import_kwh", None),
    ("IIoT.LineCounter.Mqtt", "count_total", 50.),
    ("Logistics.AGVVehicle.Mqtt", "pos_x_m", 10.),
    ("Building.RobotVacuum.Mqtt", "area_cleaned_m2", 1.1 / 6.),
])
def test_accumulation_tracks_elapsed_time_and_repeated_samples_do_not_add_time(model_id, output, expected, times):
    definition, values = model(model_id)
    values.update(mission_state="navigating", speed_mps=1., target_speed_mps=1., target_x_m=100.,
                  target_y_m=0., heading_deg=0., line_speed_mpm=30., target_speed_mpm=30.,
                  desired_cleaning=1)
    if model_id == "Energy.EnergyMeter3Ph.Mqtt":
        values["voltage_drop_per_amp"] = 0.
        values["voltage_unbalance_gain"] = 0.
        values["voltage_l1"] = values["voltage_nominal"]
        values["voltage_l2"] = values["voltage_nominal"]
        values["voltage_l3"] = values["voltage_nominal"]
    baseline = values[output]
    for time in times:
        tick(definition, values, time)
    if expected is None:
        expected = values["active_power_kw"] * 10. / 3600.
    assert values[output] - baseline == pytest.approx(expected)
    before = values[output]
    # Resetting the clock must not integrate a negative step or old uptime.
    tick(definition, values, 0.)
    assert values[output] == before


@pytest.mark.parametrize("trigger", ["battery", "bin", "command"])
def test_robot_returns_docks_and_does_not_resume_the_stale_clean_request(trigger):
    definition, values = model("Building.RobotVacuum.Mqtt")
    values.update(desired_cleaning=1, return_duration_s=3.)
    tick(definition, values, 0.)
    assert values["cleaning_active"] == 1 and values["docked"] == 0
    values[{"battery": "battery_percent", "bin": "bin_fill_percent", "command": "dock_request"}[trigger]] = {
        "battery": 14., "bin": 97., "command": 1,
    }[trigger]
    tick(definition, values, 1.)
    assert values["returning_home"] == 1
    assert values["cleaning_active"] == 0
    assert values["desired_cleaning"] == 0
    tick(definition, values, 3.)
    tick(definition, values, 4.)
    assert values["docked"] == 1
    assert values["returning_home"] == 0
    assert values["dock_request"] == 0
    # A serviced bin or recharged battery must not restart a previous mission.
    values.update(battery_percent=100., bin_fill_percent=5.)
    tick(definition, values, 5.)
    assert values["status_text"] == "DOCKED"
    assert values["cleaning_active"] == 0


def test_agv_obstacle_command_stops_motion_in_the_same_cycle():
    definition, values = model("Logistics.AGVVehicle.Mqtt")
    values.update(mission_state="navigating", speed_mps=1., target_x_m=100.)
    tick(definition, values, 0.)
    before = values["pos_x_m"]
    values["alarm_obstacle"] = 1
    tick(definition, values, 1.)
    assert values["speed_mps"] == 0.
    assert values["pos_x_m"] == before
    assert values["mission_state"] == "error"


@pytest.mark.parametrize("target", [(25., 12.), (-10., -4.)])
def test_agv_reaches_an_off_axis_waypoint_without_overshooting_and_returns_after_scenario(target):
    definition, values = model("Logistics.AGVVehicle.Mqtt")
    values.update(target_x_m=target[0], target_y_m=target[1], target_speed_mps=1.4)
    for time in (0., 1., 10., 100.):
        tick(definition, values, time)
    assert values["pos_x_m"] == pytest.approx(target[0])
    assert values["pos_y_m"] == pytest.approx(target[1])
    assert values["mission_state"] == "waiting"
    assert values["speed_mps"] == 0.
    # Restoring the original target after a scenario must turn the vehicle back.
    values.update(target_x_m=10., target_y_m=0.)
    for time in (101., 102., 200.):
        tick(definition, values, time)
    assert values["pos_x_m"] == pytest.approx(10.)
    assert values["pos_y_m"] == pytest.approx(0.)
    assert values["mission_state"] == "waiting"


def test_agv_manual_heading_mode_preserves_heading_commands():
    definition, values = model("Logistics.AGVVehicle.Mqtt")
    values.update(k__autonomous_navigation=False, heading_deg=90., mission_state="navigating",
                  speed_mps=1., target_speed_mps=1., target_x_m=100.)
    tick(definition, values, 0.)
    tick(definition, values, 1.)
    assert values["heading_deg"] == 90.
    assert values["pos_x_m"] == pytest.approx(0., abs=1e-10)
    assert values["pos_y_m"] == pytest.approx(1.)
