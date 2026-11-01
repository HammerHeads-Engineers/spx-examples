"""Regressions found by full-catalog runtime qualification."""

from pathlib import Path

import pytest
import yaml

from tools.validate_models import ValidationResult, validate_model_file

ROOT = Path(__file__).resolve().parents[3]
PLUG = ROOT / "library/domains/building/actuator/generic/smart_plug__matter.yaml"
THERMOSTAT = (
    ROOT / "library/domains/building/thermostat/generic/thermostat__matter.yaml"
)


def test_smart_plug_on_off_remain_matter_command_names_after_yaml_loading():
    model = yaml.safe_load(PLUG.read_text(encoding="utf-8"))
    bindings = {
        row["name"]: row for row in model["communication"][0]["matter"]["bindings"]
    }
    assert bindings["plug_command_on"]["command"] == "On"
    assert bindings["plug_command_off"]["command"] == "Off"


@pytest.mark.parametrize("token", ["On", "Off"])
def test_validator_explains_unquoted_matter_boolean_commands(tmp_path, token):
    model = yaml.safe_load(
        f"attributes: {{value: 0}}\ncommunication:\n- matter:\n    bindings:\n    - name: switch\n      command: {token}\n"
    )
    result = ValidationResult()
    validate_model_file(tmp_path / "plug.yaml", model, result)
    assert any("quote command names" in error for error in result.errors)


@pytest.mark.parametrize("path", [PLUG, THERMOSTAT])
def test_matter_transport_and_commissioned_device_are_instance_parameters(path):
    model = yaml.safe_load(path.read_text(encoding="utf-8"))
    config = model["communication"][0]["matter"]
    parameters = model["meta_parameters"]
    assert config["controller"]["ws_url"] == "$param(matter_server_ws_url)"
    assert config["controller"]["fabric_id"] == "$param(matter_fabric_id)"
    assert parameters["matter_server_ws_url"]["default"] == "ws://matter-server:5580/ws"
    assert parameters["matter_node_id"]["default"] == "0x1234"
    for binding in config["bindings"]:
        assert binding["node_id"] == "$param(matter_node_id)"
        assert binding["endpoint"] == "$param(matter_endpoint)"
