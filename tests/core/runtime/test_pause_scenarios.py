"""Pause regression with real runtime clocks, energy and scenario deadlines."""

import os
import time

import pytest


pytestmark = pytest.mark.skipif(os.getenv("SPX_MODEL_RUNTIME_TESTS") != "1", reason="requires SPX runtime")


@pytest.mark.parametrize("step", [0.1, 0.25])
def test_pause_preserves_energy_and_single_step_integrates_once(step):
    from spx_core.system import Model
    model = Model(name="pause_energy", definition={
        "timer": {"step": step}, "polling": {"interval": 0.01},
        "attributes": {"energy_wh": 0.0, "_last_time_s": 0.0},
        "actions": [
            {"function": "$in(energy_wh)", "call": "$in(energy_wh) + 3600 * ($in(__timer) - $in(_last_time_s)) / 3600"},
            {"function": "$in(_last_time_s)", "call": "$in(__timer)"},
        ],
    })
    try:
        model.start()
        time.sleep(0.03)
        model.pause()
        energy = model["attributes"]["energy_wh"].internal_value
        last_sample = model["attributes"]["_last_time_s"].internal_value
        clock = model["timer"].time
        time.sleep(0.06)
        assert model["attributes"]["energy_wh"].internal_value == energy
        assert model["timer"].time == clock
        model.run()
        assert model["timer"].time == pytest.approx(clock + step)
        expected = energy + clock + step - last_sample
        assert model["attributes"]["energy_wh"].internal_value == pytest.approx(expected)
        assert model.state.name == "PAUSED"
        frozen = model["attributes"]["energy_wh"].internal_value
        time.sleep(0.06)
        assert model["attributes"]["energy_wh"].internal_value == frozen
        model.start()
        time.sleep(0.03)
        assert frozen < model["attributes"]["energy_wh"].internal_value < frozen + 0.06
    finally:
        model.destroy()


def test_scenario_keeps_remaining_duration_and_cycles():
    from spx_core.system.scenarios import Scenario
    scenario = Scenario(name="pause_scenario", definition={"enabled": True, "period": 0.02,
                                                           "duration": 0.15, "run_limit": 50})
    try:
        scenario.start()
        time.sleep(0.04)
        scenario.pause()
        budget = scenario._runs_remaining
        elapsed = scenario["timer"].time
        time.sleep(0.2)
        assert scenario.active
        assert scenario._runs_remaining == budget
        assert scenario["timer"].time == elapsed
        scenario.start()
        time.sleep(0.15)
        assert not scenario.active
    finally:
        scenario.destroy()
