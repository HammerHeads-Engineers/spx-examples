# SPDX-License-Identifier: MIT
"""Unit tests for platform-aware installer selection pruning."""

from __future__ import annotations

from pathlib import Path

from installer import manifest
from installer.selection import (
    apply_platform_compatibility,
    resolve_model_ids,
    resolve_protocol_model_ids,
    resolve_protocol_service_ids,
    resolve_service_ids,
)


def build_index() -> manifest.ManifestIndex:
    services = {
        "btvirt_adapter": manifest.ServiceManifest(
            id="btvirt_adapter",
            name="btvirt Adapter",
            protocol="ble",
            description="Fake BLE adapter",
            ports=[
                manifest.ServicePort(
                    transport="tcp", host=8085, container=8085, purpose="BLE bridge"
                )
            ],
            deployment=manifest.ServiceDeployment(
                runtime="native",
                instructions={
                    "macos": "Install via Homebrew.",
                    "linux": "Install from source.",
                    "windows": "Not supported yet; use WSL2 or external BLE bridge",
                },
                commands={
                    "macos": ["bash", "setup_btvirt_macos.sh"],
                    "linux": ["bash", "setup_btvirt_linux.sh"],
                },
            ),
        ),
        "mqtt_broker": manifest.ServiceManifest(
            id="mqtt_broker",
            name="MQTT Broker",
            protocol="mqtt",
            description="Test broker",
            ports=[
                manifest.ServicePort(
                    transport="tcp", host=1883, container=1883, purpose="telemetry"
                )
            ],
            deployment=manifest.ServiceDeployment(
                runtime="docker", image="eclipse-mosquitto"
            ),
        ),
    }
    models = {
        "ble_monitor": manifest.ModelManifest(
            id="ble_monitor",
            name="BLE Vital Signs Monitor",
            path=Path(
                "library/domains/lab/monitor/generic/vital_signs_monitor__ble_gatt.yaml"
            ),
            domain="lab",
            protocols=["ble"],
            services=["btvirt_adapter"],
            packages=["embedded_lab_pack"],
            profiles=["mhealth_ci"],
            domain_group="lab",
            device_class="monitor",
            vendor="generic",
        ),
        "mqtt_sensor": manifest.ModelManifest(
            id="mqtt_sensor",
            name="MQTT Environment Sensor",
            path=Path(
                "library/domains/environment/sensor/generic/environment_sensor__mqtt.yaml"
            ),
            domain="environment",
            protocols=["mqtt"],
            services=["mqtt_broker"],
            packages=["embedded_lab_pack"],
            profiles=[],
            domain_group="environment",
            device_class="sensor",
            vendor="generic",
        ),
    }
    return manifest.ManifestIndex(
        services=services,
        models=models,
        domains={},
        industries={},
        profiles={},
    )


def test_apply_platform_compatibility_filters_ble_on_windows() -> None:
    index = build_index()

    adjustment = apply_platform_compatibility(
        model_ids=["ble_monitor", "mqtt_sensor"],
        service_ids=["btvirt_adapter", "mqtt_broker"],
        instances=[
            {"model_id": "ble_monitor", "instance_key": "spx_health_monitor_ble"},
            {"model_id": "mqtt_sensor", "instance_key": "spx_env_sensor_mqtt"},
        ],
        start_instances=["spx_health_monitor_ble", "spx_env_sensor_mqtt"],
        index=index,
        platform_name="windows",
    )

    assert adjustment.model_ids == ["mqtt_sensor"]
    assert adjustment.service_ids == ["mqtt_broker"]
    assert adjustment.instances == [
        {"model_id": "mqtt_sensor", "instance_key": "spx_env_sensor_mqtt"}
    ]
    assert adjustment.start_instances == ["spx_env_sensor_mqtt"]
    assert adjustment.warnings
    assert (
        "Windows does not support btvirt Adapter (BLE/GATT, btvirt_adapter)"
        in adjustment.warnings[0]
    )
    assert "BLE Vital Signs Monitor" in adjustment.warnings[0]
    assert "spx_health_monitor_ble" in adjustment.warnings[0]


def test_apply_platform_compatibility_keeps_ble_on_linux() -> None:
    index = build_index()

    adjustment = apply_platform_compatibility(
        model_ids=["ble_monitor", "mqtt_sensor"],
        service_ids=["btvirt_adapter", "mqtt_broker"],
        instances=[
            {"model_id": "ble_monitor", "instance_key": "spx_health_monitor_ble"},
            {"model_id": "mqtt_sensor", "instance_key": "spx_env_sensor_mqtt"},
        ],
        start_instances=["spx_health_monitor_ble", "spx_env_sensor_mqtt"],
        index=index,
        platform_name="linux",
    )

    assert adjustment.model_ids == ["ble_monitor", "mqtt_sensor"]
    assert adjustment.service_ids == ["btvirt_adapter", "mqtt_broker"]
    assert adjustment.instances == [
        {"model_id": "ble_monitor", "instance_key": "spx_health_monitor_ble"},
        {"model_id": "mqtt_sensor", "instance_key": "spx_env_sensor_mqtt"},
    ]
    assert adjustment.start_instances == [
        "spx_health_monitor_ble",
        "spx_env_sensor_mqtt",
    ]
    assert adjustment.warnings == []


def test_protocol_resolvers_use_catalog_protocols_only() -> None:
    index = build_index()

    assert resolve_protocol_model_ids(["mqtt"], index) == ["mqtt_sensor"]
    assert resolve_protocol_service_ids(["mqtt"], index) == ["mqtt_broker"]


def test_protocol_model_and_service_resolution_does_not_change_package_resolution() -> (
    None
):
    index = build_index()

    assert resolve_model_ids([], [], ["mqtt"], index) == ["mqtt_sensor"]
    assert resolve_service_ids(["mqtt_sensor"], [], [], index) == ["mqtt_broker"]
