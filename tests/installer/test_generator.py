# SPDX-License-Identifier: MIT
"""Tests for deployment generator."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from installer.generator import DeploymentGenerator
from installer.manifest import (
    DomainManifest,
    IndustryManifest,
    ManifestIndex,
    ModelManifest,
    ProfileManifest,
    ServiceDeployment,
    ServiceManifest,
    ServicePort,
)
from installer.wizard import WizardSelection


def build_index() -> ManifestIndex:
    services = {
        "mqtt_broker": ServiceManifest(
            id="mqtt_broker",
            name="MQTT Broker",
            protocol="mqtt",
            description="Test broker",
            ports=[ServicePort(transport="tcp", host=1883, container=1883, purpose="telemetry")],
            deployment=ServiceDeployment(
                runtime="docker",
                image="eclipse-mosquitto:latest",
                container_name="mosquitto-test",
                volumes=["./library/assets/mosquitto/mosquitto.conf:/config:ro"],
            ),
        ),
        "modbus_tcp_gateway": ServiceManifest(
            id="modbus_tcp_gateway",
            name="Modbus",
            protocol="modbus",
            description="Built-in",
            ports=[ServicePort(transport="tcp", host=502, container=502, purpose="modbus")],
            deployment=ServiceDeployment(runtime="builtin"),
        ),
    }
    models = {
        "sensor": ModelManifest(
            id="sensor",
            name="Sensor",
            path=Path("library/domains/iot/sensor.yaml"),
            domain="iot",
            protocols=["mqtt"],
            services=["mqtt_broker", "modbus_tcp_gateway"],
            packages=["pack_a"],
            profiles=[],
        )
    }
    domains = {
        "iot": DomainManifest(
            id="iot",
            name="IoT",
            description="Domain",
            path=Path("library/domains/iot"),
        )
    }
    industries = {
        "pack_a": IndustryManifest(
            id="pack_a",
            name="Pack A",
            description="Pack",
            protocols=["mqtt"],
            services=["mqtt_broker"],
            profiles=[],
            path=Path("library/industries/pack_a"),
            default_instances=[{"model": "sensor", "instance": "inst_001"}],
        )
    }
    profiles: dict[str, ProfileManifest] = {}
    return ManifestIndex(
        services=services,
        models=models,
        domains=domains,
        industries=industries,
        profiles=profiles,
    )


def test_generator_creates_compose(tmp_path: Path) -> None:
    index = build_index()
    generator = DeploymentGenerator(index)
    selection = WizardSelection(
        packages=["pack_a"],
        profiles=[],
        protocols=[],
        install_examples=True,
        install_spx_ui=False,
        offline_bundle=False,
        license_key="ABC-123",
        model_ids=["sensor"],
        service_ids=["mqtt_broker", "modbus_tcp_gateway"],
    )

    output_dir = tmp_path / "out"
    generator.generate(selection, output_dir)

    compose_path = output_dir / "docker-compose.generated.yml"
    assert compose_path.exists()
    data = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    services = data["services"]
    assert "spx-server" in services
    assert "mqtt_broker" in services
    assert "8000:8000" in services["spx-server"]["ports"]
    assert "502:502" in services["spx-server"]["ports"]
    assert "1883:1883" in services["mqtt_broker"]["ports"]
    mqtt_volumes = services["mqtt_broker"].get("volumes", [])
    assert any(vol.startswith("./assets/mosquitto/mosquitto.conf") for vol in mqtt_volumes)

    env_path = output_dir / ".env"
    assert env_path.read_text(encoding="utf-8").strip() == "SPX_PRODUCT_KEY=ABC-123"

    asset_file = output_dir / "assets" / "mosquitto" / "mosquitto.conf"
    assert asset_file.exists()

    bundle = json.loads((output_dir / "bundle.json").read_text(encoding="utf-8"))
    assert bundle["license_key"] == "ABC-123"
    assert bundle.get("services") == ["mqtt_broker", "modbus_tcp_gateway"]
    assert len(bundle["models"]) == 1
    assert bundle["models"][0]["id"] == "sensor"
    assert bundle.get("instances") == [{"model_id": "sensor", "instance_key": "inst_001"}]

    start_path = output_dir / "spx-start.sh"
    stop_path = output_dir / "spx-stop.sh"
    assert start_path.exists()
    assert stop_path.exists()
    start_content = start_path.read_text(encoding="utf-8")
    stop_content = stop_path.read_text(encoding="utf-8")
    assert "BLE_ADAPTER_PID" in start_content
    assert "trap cleanup_on_failure ERR INT TERM" in start_content
    assert "down --remove-orphans" in start_content
    assert "docker compose" in start_content
    assert "pkill -f spx-ble-adapter" in stop_content
    start_ps_path = output_dir / "spx-start.ps1"
    stop_ps_path = output_dir / "spx-stop.ps1"
    assert start_ps_path.exists()
    assert stop_ps_path.exists()
    start_ps_content = start_ps_path.read_text(encoding="utf-8")
    stop_ps_content = stop_ps_path.read_text(encoding="utf-8")
    assert "Cleanup-OnFailure" in start_ps_content
    assert "Start-Process \"spx-ble-adapter\"" in start_ps_content
    assert "docker compose -f (Join-Path $ScriptDir \"docker-compose.generated.yml\")" in start_ps_content
    assert "Get-CimInstance Win32_Process" in stop_ps_content
