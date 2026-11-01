import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location(
    "temperature_quickstart", ROOT / "examples/core/temperature_quickstart.py"
)
example = importlib.util.module_from_spec(spec)
spec.loader.exec_module(example)


class Attribute:
    def __init__(self, value):
        self.internal_value = value


class Instance:
    def __init__(self, fail=False):
        self.attributes = {
            name: Attribute(20.0) for name in ("k__temperature_c", "temperature_c")
        }
        self.state = "INITIALIZED"
        self.fail = fail

    def __getitem__(self, key):
        assert key == "attributes"
        return self.attributes

    def reset(self):
        pass

    def start(self):
        self.state = "RUNNING"

    def stop(self):
        self.state = "STOPPED"

    def run(self):
        if self.fail:
            raise RuntimeError("simulated runtime failure")
        self.attributes["temperature_c"].internal_value = self.attributes[
            "k__temperature_c"
        ].internal_value


class Instances(dict):
    def __init__(self, fail=False):
        super().__init__()
        self.fail = fail

    def __setitem__(self, key, value):
        super().__setitem__(key, Instance(fail=self.fail))


@pytest.mark.parametrize("fail", [False, True])
def test_example_cleans_up_only_owned_objects_even_when_verification_fails(fail):
    existing_model = {"attributes": {"x": 1}}
    client = {
        "models": {"user_model": existing_model},
        "instances": Instances(fail=fail),
    }
    client["instances"]["user_instance"] = "user_model"
    user_instance = client["instances"]["user_instance"]
    if fail:
        with pytest.raises(RuntimeError, match="simulated runtime"):
            example.run_example(client, {}, token="test")
    else:
        assert example.run_example(client, {}, token="test") == (20.0, 37.5)
    assert client["models"] == {"user_model": existing_model}
    assert client["instances"] == {"user_instance": user_instance}
    assert user_instance.state == "INITIALIZED"


def test_example_refuses_a_collision_without_cleanup_or_replacement():
    existing = {"attributes": {"x": 1}}
    client = {
        "models": {"quickstart_temperature_test": existing},
        "instances": Instances(),
    }
    with pytest.raises(example.QuickstartError, match="no objects were changed"):
        example.run_example(client, {}, token="test")
    assert client["models"]["quickstart_temperature_test"] is existing
    assert not client["instances"]
