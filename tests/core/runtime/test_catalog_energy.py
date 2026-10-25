"""Compare modeled energy with the physical integral of reported power."""

import os
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
ENERGY = ("energy_consumption_kwh", "energy_today_kwh", "pv_energy_total_kwh", "energy_wh", "energy_consumed_kwh", "energy_import_kwh", "energy_import_total_kwh", "k__energy_import_total_kwh", "energy_import_total_wh", "k__energy_import_total_wh", "device_energy_kwh")
POWER = ("power_draw_kw", "lighting_power_kw", "pv_power_w", "power_kw", "active_power_sum_w", "active_power_kw", "active_power_total_w", "k__active_power_total_w", "k__active_power_total_kw", "active_power_total_kw", "device_real_load_power_kw")
CASES = []
for entry in yaml.safe_load((ROOT / "library/catalog/models.yaml").read_text(encoding="utf-8"))["models"]:
    definition = yaml.safe_load((ROOT / entry["path"]).read_text(encoding="utf-8"))
    attributes = definition.get("attributes", {})
    energy = next((name for name in ENERGY if name in attributes), None)
    power = next((name for name in POWER if name in attributes), None)
    if energy and power:
        CASES.append((entry, energy, power))
pytestmark = pytest.mark.skipif(os.getenv("SPX_MODEL_RUNTIME_TESTS") != "1", reason="requires SPX action runtime")


@pytest.mark.parametrize("step", [0.1, 0.25])
@pytest.mark.parametrize("entry,energy,power", CASES, ids=[item[0]["id"] for item in CASES])
def test_power_integral_matches_energy(entry, energy, power, step):
    from spx_core.system import Model
    from spx_core.system.param_resolver import resolve_definition_with_params
    definition = yaml.safe_load((ROOT / entry["path"]).read_text(encoding="utf-8"))
    definition, _ = resolve_definition_with_params(definition, specs=definition.get("meta_parameters", {}),
        provided={}, allow_defaults=True, require_declared=True)
    definition.pop("communication", None)
    definition.pop("scenarios", None)
    instance = Model(name="qa_energy", definition=definition)
    instance.real_time = False
    try:
        instance.reset()
        instance.prepare()
        attrs = instance["attributes"]
        if entry["id"] == "Energy.EVSE.Ocpp":
            attrs["session_active"].internal_value = 1
            attrs["commanded_current_a"].internal_value = 16
        instance["timer"].time = 0
        instance.run()
        before = attrs[energy].internal_value
        integral = 0
        for tick in range(1, 101):
            instance["timer"].time = tick * step
            instance.run()
            watts = attrs[power].internal_value * (1000 if power.endswith("_kw") else 1)
            integral += watts * step / 3600 / (1000 if energy.endswith("_kwh") else 1)
        assert integral > 0, "A zero-load test cannot prove energy integration"
        assert attrs[energy].internal_value - before == pytest.approx(integral, rel=0.02)
        paused = attrs[energy].internal_value
        for _ in range(10):
            instance.run()
        assert attrs[energy].internal_value == pytest.approx(paused)
    finally:
        instance.destroy()
