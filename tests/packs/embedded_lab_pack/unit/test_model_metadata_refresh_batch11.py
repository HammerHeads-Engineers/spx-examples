# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path

import yaml

from tests.common.repo import repo_root


ROOT = repo_root()


def _load_yaml(relative_path: str) -> dict:
    path = ROOT / Path(relative_path)
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _pack_models() -> list[tuple[str, str]]:
    pack_index = _load_yaml("library/industries/embedded_lab_pack/MODELS.yaml")
    return [(entry["id"], entry["path"]) for entry in pack_index["models"]]


def _communication_blocks(model: dict) -> list[dict]:
    communication = model.get("communication") or []
    if isinstance(communication, dict):
        return [communication]
    if isinstance(communication, list):
        return [block for block in communication if isinstance(block, dict)]
    return []


def _has_meta_parameter(meta_parameters: dict, name: str, type_name: str) -> bool:
    spec = meta_parameters.get(name)
    return isinstance(spec, dict) and spec.get("type") == type_name


def _missing_ascii_endpoint(
    model_id: str, block: dict, meta_parameters: dict
) -> str | None:
    config = block.get("ascii")
    if not isinstance(config, dict):
        return None
    if not _has_meta_parameter(meta_parameters, "ascii_port", "int"):
        return f"{model_id}:ascii"
    if config.get("port") != "$param(ascii_port)":
        return f"{model_id}:ascii"
    return None


def _missing_ble_endpoint(
    model_id: str, block: dict, meta_parameters: dict
) -> str | None:
    config = block.get("ble")
    if not isinstance(config, dict):
        return None
    if not _has_meta_parameter(meta_parameters, "ble_adapter_base_url", "str"):
        return f"{model_id}:ble"
    if not _has_meta_parameter(meta_parameters, "ble_device_name", "str"):
        return f"{model_id}:ble"
    if config.get("adapter", {}).get("baseUrl") != "$param(ble_adapter_base_url)":
        return f"{model_id}:ble"
    if config.get("device", {}).get("name") != "$param(ble_device_name)":
        return f"{model_id}:ble"
    return None


def _missing_mqtt_endpoint(
    model_id: str, block: dict, meta_parameters: dict
) -> str | None:
    config = block.get("mqtt")
    if not isinstance(config, dict):
        return None
    if not _has_meta_parameter(meta_parameters, "mqtt_broker_host", "str"):
        return f"{model_id}:mqtt"
    if not _has_meta_parameter(meta_parameters, "mqtt_broker_port", "int"):
        return f"{model_id}:mqtt"
    if config.get("broker") != "$param(mqtt_broker_host)":
        return f"{model_id}:mqtt"
    if config.get("port") != "$param(mqtt_broker_port)":
        return f"{model_id}:mqtt"
    return None


def _missing_lwm2m_endpoint(
    model_id: str, block: dict, meta_parameters: dict
) -> str | None:
    config = block.get("lwm2m")
    if not isinstance(config, dict):
        return None
    expected_parameters = (
        ("lwm2m_endpoint", "str"),
        ("lwm2m_server_host", "str"),
        ("lwm2m_server_port", "int"),
        ("lwm2m_server_endpoint", "str"),
    )
    if any(not _has_meta_parameter(meta_parameters, name, type_name)
           for name, type_name in expected_parameters):
        return f"{model_id}:lwm2m"
    if config.get("client", {}).get("endpoint") != "$param(lwm2m_endpoint)":
        return f"{model_id}:lwm2m"
    if config.get("server", {}).get("host") != "$param(lwm2m_server_host)":
        return f"{model_id}:lwm2m"
    if config.get("server", {}).get("port") != "$param(lwm2m_server_port)":
        return f"{model_id}:lwm2m"
    if config.get("server", {}).get("endpoint") != "$param(lwm2m_server_endpoint)":
        return f"{model_id}:lwm2m"
    return None


def _missing_modbus_endpoint(
    model_id: str, block: dict, meta_parameters: dict
) -> str | None:
    config = block.get("modbus_slave")
    if not isinstance(config, dict):
        return None
    if not _has_meta_parameter(meta_parameters, "modbus_port", "int"):
        return f"{model_id}:modbus_slave"
    if not _has_meta_parameter(meta_parameters, "modbus_unit_id", "int"):
        return f"{model_id}:modbus_slave"
    if config.get("port") != "$param(modbus_port)":
        return f"{model_id}:modbus_slave"
    if config.get("unit_id") != "$param(modbus_unit_id)":
        return f"{model_id}:modbus_slave"
    return None


def _missing_communication_endpoints(model_id: str, model: dict) -> list[str]:
    meta_parameters = model.get("meta_parameters") or {}
    checkers = (
        _missing_ascii_endpoint,
        _missing_ble_endpoint,
        _missing_mqtt_endpoint,
        _missing_lwm2m_endpoint,
        _missing_modbus_endpoint,
    )
    missing = []
    for block in _communication_blocks(model):
        for checker in checkers:
            if (issue := checker(model_id, block, meta_parameters)) is not None:
                missing.append(issue)
    return missing


def _missing_mapping_names(model_id: str, model: dict) -> list[str]:
    missing = []
    for block in _communication_blocks(model):
        config = block.get("ascii")
        if not isinstance(config, dict):
            continue
        for command, mapping in (config.get("mappings") or {}).items():
            if not isinstance(mapping, dict) or not mapping.get("name"):
                missing.append(f"{model_id}:ascii:{command}")
    return missing


def test_embedded_lab_pack_communication_endpoints_use_meta_parameters() -> None:
    missing = []
    for model_id, relative_path in _pack_models():
        missing.extend(_missing_communication_endpoints(model_id, _load_yaml(relative_path)))
    assert missing == []


def test_embedded_lab_pack_scpi_mappings_have_explicit_names() -> None:
    missing = []
    for model_id, relative_path in _pack_models():
        missing.extend(_missing_mapping_names(model_id, _load_yaml(relative_path)))
    assert missing == []


def test_ble_models_use_configurable_adapter_endpoint_and_device_name() -> None:
    temperature_sensor = _load_yaml("library/domains/lab/sensor/generic/temperature_sensor__ble_gatt.yaml")
    temperature_ble = temperature_sensor["communication"][0]["ble"]
    assert temperature_sensor["meta_parameters"]["ble_adapter_base_url"]["default"] == (
        "http://host.docker.internal:8085"
    )
    assert temperature_sensor["meta_parameters"]["ble_device_name"]["default"] == (
        "SpX Temperature Sensor"
    )
    assert temperature_ble["adapter"]["baseUrl"] == "$param(ble_adapter_base_url)"
    assert temperature_ble["device"]["name"] == "$param(ble_device_name)"

    vital_signs = _load_yaml("library/domains/lab/monitor/generic/vital_signs_monitor__ble_gatt.yaml")
    vital_ble = vital_signs["communication"][0]["ble"]
    assert vital_signs["meta_parameters"]["ble_adapter_base_url"]["default"] == (
        "http://host.docker.internal:8085"
    )
    assert vital_signs["meta_parameters"]["ble_device_name"]["default"] == "SPX-Sim"
    assert vital_ble["adapter"]["baseUrl"] == "$param(ble_adapter_base_url)"
    assert vital_ble["device"]["name"] == "$param(ble_device_name)"
