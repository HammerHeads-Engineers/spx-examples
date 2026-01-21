# SPDX-License-Identifier: MIT
"""Tests for deployment generator."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from installer.generator import DeploymentGenerator, SPX_UI_IMAGE
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
        "bacnet_gateway": ServiceManifest(
            id="bacnet_gateway",
            name="BACnet/IP",
            protocol="bacnet",
            description="Built-in",
            ports=[
                ServicePort(transport="udp", host=47808, container=47808, purpose="bacnet flexit"),
                ServicePort(transport="udp", host=47818, container=47818, purpose="bacnet security"),
                ServicePort(transport="udp", host=47828, container=47828, purpose="bacnet fire"),
            ],
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
        instances=[{"model_id": "sensor", "instance_key": "inst_001"}],
        start_instances=["inst_001"],
    )

    output_dir = tmp_path / "out"
    generator.generate(selection, output_dir)

    compose_path = output_dir / "docker-compose.generated.yml"
    assert compose_path.exists()
    data = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    services = data["services"]
    assert "spx-server" in services
    assert "spx-ui" not in services
    assert "mqtt_broker" in services
    assert "8000:8000" in services["spx-server"]["ports"]
    assert "host.docker.internal:host-gateway" in services["spx-server"].get("extra_hosts", [])
    assert "502:502" in services["spx-server"]["ports"]
    assert "1883:1883" in services["mqtt_broker"]["ports"]
    mqtt_volumes = services["mqtt_broker"].get("volumes", [])
    assert any(vol.startswith("./assets/mosquitto/mosquitto.conf") for vol in mqtt_volumes)

    env_path = output_dir / ".env"
    assert env_path.read_text(encoding="utf-8").strip() == "SPX_PRODUCT_KEY=ABC-123"

    asset_file = output_dir / "assets" / "mosquitto" / "mosquitto.conf"
    assert asset_file.exists()
    assert (output_dir / "extensions").exists()

    bundle = json.loads((output_dir / "bundle.json").read_text(encoding="utf-8"))
    assert bundle["license_key"] == "ABC-123"
    assert bundle.get("services") == ["mqtt_broker", "modbus_tcp_gateway"]
    assert len(bundle["models"]) == 1
    assert bundle["models"][0]["id"] == "sensor"
    assert bundle.get("instances") == [{"model_id": "sensor", "instance_key": "inst_001"}]
    assert bundle.get("start_instances") == ["inst_001"]

    start_path = output_dir / "spx-start.sh"
    stop_path = output_dir / "spx-stop.sh"
    assert start_path.exists()
    assert stop_path.exists()
    runner_path = output_dir / "bootstrap_runner.py"
    assert runner_path.exists()
    start_content = start_path.read_text(encoding="utf-8")
    stop_content = stop_path.read_text(encoding="utf-8")
    assert "BLE_ADAPTER_PID" in start_content
    assert "trap cleanup_on_failure ERR INT TERM" in start_content
    assert "down --remove-orphans" in start_content
    assert "docker compose" in start_content
    assert "bootstrap_runner.py" in start_content
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
    assert "bootstrap_runner.py" in start_ps_content
    assert "Get-CimInstance Win32_Process" in stop_ps_content


def test_generator_includes_ui_when_requested(tmp_path: Path) -> None:
    index = build_index()
    generator = DeploymentGenerator(index)
    selection = WizardSelection(
        packages=["pack_a"],
        profiles=[],
        protocols=[],
        install_examples=True,
        install_spx_ui=True,
        offline_bundle=False,
        license_key="KEY-456",
        model_ids=["sensor"],
        service_ids=["mqtt_broker", "modbus_tcp_gateway"],
        instances=[{"model_id": "sensor", "instance_key": "inst_001"}],
        start_instances=["inst_001"],
    )

    output_dir = tmp_path / "out-ui"
    generator.generate(selection, output_dir)

    compose_path = output_dir / "docker-compose.generated.yml"
    data = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    services = data["services"]
    assert "spx-ui" in services
    ui_service = services["spx-ui"]
    assert ui_service["image"] == SPX_UI_IMAGE
    assert ui_service["ports"] == ["3000:3000"]
    assert ui_service["environment"]["SPX_PRODUCT_KEY"] == "${SPX_PRODUCT_KEY}"
    assert ui_service["command"] == ["--product-key", "${SPX_PRODUCT_KEY}"]
    assert ui_service["depends_on"]["spx-server"]["condition"] == "service_healthy"


def test_generator_formats_bacnet_ports_with_bind_addr(tmp_path: Path) -> None:
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
        service_ids=["mqtt_broker", "modbus_tcp_gateway", "bacnet_gateway"],
        instances=[{"model_id": "sensor", "instance_key": "inst_001"}],
        start_instances=["inst_001"],
    )

    output_dir = tmp_path / "out-bacnet"
    generator.generate(selection, output_dir)

    compose_path = output_dir / "docker-compose.generated.yml"
    data = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    ports = data["services"]["spx-server"]["ports"]
    assert "${BACNET_BIND_ADDR:-127.0.0.1}:47808:47808/udp" in ports
    assert "${BACNET_BIND_ADDR:-127.0.0.1}:47818:47818/udp" in ports
    assert "${BACNET_BIND_ADDR:-127.0.0.1}:47828:47828/udp" in ports
