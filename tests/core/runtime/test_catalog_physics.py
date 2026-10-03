"""Deterministic action/scenario smoke checks for the complete model catalog.

Transport diagnostics and callbacks belong to protocol qualification, not this
physics-only test. Their explicit names are recorded in the JUnit properties.
No scenario assertion is converted into a successful parent test.
"""

import copy
import math
import os
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
MODELS = yaml.safe_load((ROOT / "library/catalog/models.yaml").read_text(encoding="utf-8"))["models"]
pytestmark = pytest.mark.skipif(os.getenv("SPX_MODEL_RUNTIME_TESTS") != "1", reason="requires SPX action runtime")


@pytest.mark.parametrize("entry", MODELS, ids=[entry["id"] for entry in MODELS])
def test_model_actions_and_scenario_overrides_are_finite(entry, record_property):
    from spx_core.system import Model
    from spx_core.system.param_resolver import resolve_definition_with_params
    definition = yaml.safe_load((ROOT / entry["path"]).read_text(encoding="utf-8"))
    definition, _ = resolve_definition_with_params(
        definition, specs=definition.get("meta_parameters", {}), provided={},
        allow_defaults=True, require_declared=True,
    )
    definition.pop("communication", None)
    transport_actions = [action.get("name") for action in definition.get("actions", [])
                         if "$attr(communication." in str(action.get("call", ""))]
    record_property("protocol_diagnostics", ",".join(transport_actions))
    definition["actions"] = [action for action in definition.get("actions", [])
                             if "$attr(communication." not in str(action.get("call", ""))]
    transport_callbacks = []
    for name, scenario in (definition.get("scenarios") or {}).items():
        if "call" in scenario:
            transport_callbacks.append(name)
            del scenario["call"]
        scenario["enabled"] = False
    record_property("protocol_callbacks", ",".join(transport_callbacks))
    instance = Model(name="qa_physics", definition=copy.deepcopy(definition))
    instance.real_time = False

    def assert_healthy():
        assert instance.state.name != "FAULT", entry["id"]
        for name, attribute in instance["attributes"].children.items():
            value = attribute.internal_value
            if isinstance(value, float):
                assert math.isfinite(value), f"{entry['id']}.{name}"

    try:
        instance.reset()
        instance.prepare()
        for step in range(100):
            instance["timer"].time = step * 0.1
            instance.run()
            assert_healthy()
        for scenario in instance["scenarios"].children.values():
            instance.reset()
            instance.prepare()
            scenario.start()
            try:
                for elapsed in (0.0, 2.0, 5.0, 10.0):
                    scenario["timer"].time = elapsed
                    instance["timer"].time = elapsed
                    instance.run()
                    assert_healthy()
            finally:
                scenario.stop()
    finally:
        instance.destroy()
