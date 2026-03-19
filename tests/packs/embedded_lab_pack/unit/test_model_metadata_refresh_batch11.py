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


def test_embedded_lab_pack_communication_endpoints_use_meta_parameters() -> None:
    missing: list[str] = []

    for model_id, relative_path in _pack_models():
        model = _load_yaml(relative_path)
        meta_parameters = model.get("meta_parameters") or {}

        for block in _communication_blocks(model):
            if "ascii" in block:
                ascii_cfg = block["ascii"]
                if (
                    meta_parameters.get("ascii_port", {}).get("type") != "int"
                    or ascii_cfg.get("port") != "$param(ascii_port)"
                ):
                    missing.append(f"{model_id}:ascii")

            if "ble" in block:
                ble_cfg = block["ble"]
                if (
                    meta_parameters.get("ble_adapter_base_url", {}).get("type") != "str"
                    or meta_parameters.get("ble_device_name", {}).get("type") != "str"
                    or ble_cfg.get("adapter", {}).get("baseUrl")
                    != "$param(ble_adapter_base_url)"
                    or ble_cfg.get("device", {}).get("name") != "$param(ble_device_name)"
                ):
                    missing.append(f"{model_id}:ble")

            if "mqtt" in block:
                mqtt_cfg = block["mqtt"]
                if (
                    meta_parameters.get("mqtt_broker_host", {}).get("type") != "str"
                    or meta_parameters.get("mqtt_broker_port", {}).get("type") != "int"
                    or mqtt_cfg.get("broker") != "$param(mqtt_broker_host)"
                    or mqtt_cfg.get("port") != "$param(mqtt_broker_port)"
                ):
                    missing.append(f"{model_id}:mqtt")

            if "lwm2m" in block:
                lwm2m_cfg = block["lwm2m"]
                if (
                    meta_parameters.get("lwm2m_endpoint", {}).get("type") != "str"
                    or meta_parameters.get("lwm2m_server_host", {}).get("type") != "str"
                    or meta_parameters.get("lwm2m_server_port", {}).get("type") != "int"
                    or meta_parameters.get("lwm2m_server_endpoint", {}).get("type") != "str"
                    or lwm2m_cfg.get("client", {}).get("endpoint") != "$param(lwm2m_endpoint)"
                    or lwm2m_cfg.get("server", {}).get("host") != "$param(lwm2m_server_host)"
                    or lwm2m_cfg.get("server", {}).get("port") != "$param(lwm2m_server_port)"
                    or lwm2m_cfg.get("server", {}).get("endpoint")
                    != "$param(lwm2m_server_endpoint)"
                ):
                    missing.append(f"{model_id}:lwm2m")

            if "modbus_slave" in block:
                modbus_cfg = block["modbus_slave"]
                if (
                    meta_parameters.get("modbus_port", {}).get("type") != "int"
                    or meta_parameters.get("modbus_unit_id", {}).get("type") != "int"
                    or modbus_cfg.get("port") != "$param(modbus_port)"
                    or modbus_cfg.get("unit_id") != "$param(modbus_unit_id)"
                ):
                    missing.append(f"{model_id}:modbus_slave")

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
