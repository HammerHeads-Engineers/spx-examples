"""Cadence and payload regressions exercised by the real model action engine.

SPX_MODEL_RUNTIME_TESTS=1 requires the server SDK; release jobs must enable it.
"""

import os
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
pytestmark = pytest.mark.skipif(os.getenv("SPX_MODEL_RUNTIME_TESTS") != "1", reason="requires SPX runtime fixture")


def model(device):
    from spx_core.system import Model
    definition = yaml.safe_load((ROOT / f"library/domains/energy/{device}/generic/{device}__ocpp.yaml").read_text())
    definition.pop("communication")
    definition["scenarios"] = {}
    instance = Model(name="ocpp_regression", definition=definition)
    instance.real_time = False
    instance.reset()
    instance.prepare()
    return instance


@pytest.mark.parametrize("step", [0.1, 0.25])
def test_evse_energy_uses_elapsed_time_pause_and_reset(step):
    instance = model("evse")
    try:
        attrs = instance["attributes"]
        attrs["session_active"].internal_value = 1
        for index in range(int(10 / step) + 1):
            instance["timer"].time = index * step
            instance.run()
        expected = 6400 * 10 / 3600
        assert attrs["energy_wh"].internal_value - 1200 == pytest.approx(expected)
        assert attrs["session_energy_wh"].internal_value == pytest.approx(expected)
        for _ in range(20):
            instance.run()  # simulation time stays fixed during a pause
        assert attrs["session_energy_wh"].internal_value == pytest.approx(expected)
        instance.reset()
        attrs["session_active"].internal_value = 1
        before_reset_step = attrs["session_energy_wh"].internal_value
        instance["timer"].time = step
        instance.run()
        assert attrs["session_energy_wh"].internal_value - before_reset_step == pytest.approx(6400 * step / 3600)
    finally:
        instance.destroy()


@pytest.mark.parametrize("key", ["sampledValue", "sampled_value"])
@pytest.mark.parametrize("units,values", [(('Wh', 'W'), ('1234', '6400')), (('kWh', 'kW'), ('1.234', '6.4'))])
def test_csms_measurands_units_and_malformed_samples(key, units, values):
    instance = model("csms")
    try:
        attrs = instance["attributes"]
        attrs["last_meter_values"].internal_value = [{key: [
            {"measurand": "Current.Import", "value": "16", "unit": "A"},
            {"measurand": "Power.Active.Import", "value": values[1], "unit": units[1]},
            {"measurand": "Energy.Active.Import.Register", "value": values[0], "unit": units[0]},
        ]}]
        instance.run()
        assert attrs["last_energy_wh"].internal_value == pytest.approx(1234)
        assert attrs["last_power_w"].internal_value == pytest.approx(6400)
        for malformed in [[], [{}], [{key: [None, {}, {"measurand": "Power.Active.Import", "value": "bad"}]}],
                          [{key: [{"measurand": "Energy.Active.Import.Register", "value": "NaN"}]}]]:
            attrs["last_meter_values"].internal_value = malformed
            instance.run()
            assert attrs["last_energy_wh"].internal_value == pytest.approx(1234)
            assert attrs["last_power_w"].internal_value == pytest.approx(6400)
            assert instance.state.name != "FAULT"
    finally:
        instance.destroy()
