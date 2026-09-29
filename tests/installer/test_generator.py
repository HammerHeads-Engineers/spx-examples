# SPDX-License-Identifier: MIT
"""Tests for deployment generator."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

import yaml

from installer import manifest
from installer.generator import (
    DeploymentGenerator,
    SPX_LABEL_INSTALLATION_ID,
    SPX_LABEL_MANAGED_BY,
    SPX_LABEL_PROJECT,
    SPX_LABEL_STACK,
    SPX_SERVER_IMAGE,
    SPX_UI_IMAGE,
)
from installer.wizard import WizardSelection


def build_index() -> manifest.ManifestIndex:
    services = {
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
                runtime="docker",
                image="eclipse-mosquitto:latest",
                container_name="mosquitto-test",
                volumes=["./library/assets/mosquitto/mosquitto.conf:/config:ro"],
            ),
        ),
        "modbus_tcp_gateway": manifest.ServiceManifest(
            id="modbus_tcp_gateway",
            name="Modbus",
            protocol="modbus",
            description="Built-in",
            ports=[
                manifest.ServicePort(
                    transport="tcp", host=502, container=502, purpose="modbus"
                )
            ],
            deployment=manifest.ServiceDeployment(runtime="builtin"),
        ),
        "bacnet_gateway": manifest.ServiceManifest(
            id="bacnet_gateway",
            name="BACnet/IP",
            protocol="bacnet",
            description="Built-in",
            ports=[
                manifest.ServicePort(
                    transport="udp",
                    host=47808,
                    container=47808,
                    purpose="bacnet flexit",
                ),
                manifest.ServicePort(
                    transport="udp",
                    host=47818,
                    container=47818,
                    purpose="bacnet security",
                ),
                manifest.ServicePort(
                    transport="udp", host=47828, container=47828, purpose="bacnet fire"
                ),
            ],
            deployment=manifest.ServiceDeployment(runtime="builtin"),
        ),
        "knx_gateway": manifest.ServiceManifest(
            id="knx_gateway",
            name="KNX Gateway",
            protocol="knx",
            description="KNX/IP test gateway",
            ports=[
                manifest.ServicePort(
                    transport="udp", host=3671, container=3671, purpose="KNX/IP"
                ),
                manifest.ServicePort(
                    transport="tcp", host=6720, container=6720, purpose="knxd TCP"
                ),
            ],
            deployment=manifest.ServiceDeployment(
                runtime="docker",
                image="michelmu/knxd-docker:latest",
                container_name="knxd-test",
                volumes=["./library/assets/knx/knxd.ini:/etc/knxd.ini:ro"],
                entrypoint=["knxd", "/etc/knxd.ini"],
            ),
        ),
    }
    models = {
        "sensor": manifest.ModelManifest(
            id="sensor",
            name="Sensor",
            path=Path("library/domains/environment/sensor/generic/sensor.yaml"),
            domain="environment",
            protocols=["mqtt"],
            services=["mqtt_broker", "modbus_tcp_gateway"],
            packages=["pack_a"],
            profiles=[],
            domain_group="environment",
            device_class="sensor",
            vendor="generic",
        )
    }
    domains = {
        "environment": manifest.DomainManifest(
            id="environment",
            name="Environment",
            description="Domain",
            path=Path("library/domains/environment"),
        )
    }
    industries = {
        "pack_a": manifest.IndustryManifest(
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
    profiles: dict[str, manifest.ProfileManifest] = {}
    return manifest.ManifestIndex(
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
        service_ids=["mqtt_broker", "modbus_tcp_gateway", "knx_gateway"],
        instances=[{"model_id": "sensor", "instance_key": "inst_001"}],
        start_instances=["inst_001"],
    )

    output_dir = tmp_path / "out"
    generator.generate(selection, output_dir)

    compose_path = output_dir / "docker-compose.generated.yml"
    assert compose_path.exists()
    transaction_compose_path = output_dir / "docker-compose.transaction.yml"
    assert transaction_compose_path.exists()
    data = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    services = data["services"]
    assert data["name"] == "spx"
    assert "spx-server" in services
    assert "spx-ui" not in services
    assert "mqtt_broker" in services
    labels = services["spx-server"]["labels"]
    assert labels[SPX_LABEL_STACK] == "true"
    assert labels[SPX_LABEL_MANAGED_BY] == "installer"
    assert labels[SPX_LABEL_PROJECT] == "spx"
    assert labels[SPX_LABEL_INSTALLATION_ID]
    telemetry_path = output_dir / "telemetry.json"
    telemetry = json.loads(telemetry_path.read_text(encoding="utf-8"))
    configuration_event = telemetry["configuration_event"]
    assert telemetry["schema_version"] == 1
    assert telemetry["installation_id"] == str(
        uuid.UUID(hex=labels[SPX_LABEL_INSTALLATION_ID])
    )
    assert configuration_event["event_type"] == "installation_configured"
    assert configuration_event["installation_id"] == telemetry["installation_id"]
    assert configuration_event["occurred_at"].endswith("Z")
    assert configuration_event["metadata"]["services"] == [
        "mqtt_broker",
        "modbus_tcp_gateway",
        "knx_gateway",
    ]
    assert configuration_event["metadata"]["selection"] == {
        "packages": ["pack_a"],
        "profiles": [],
        "protocols": [],
        "install_examples": True,
        "install_spx_ui": False,
        "offline_bundle": False,
        "model_count": 1,
        "planned_instance_count": 1,
        "auto_start_instance_count": 1,
    }
    telemetry_text = telemetry_path.read_text(encoding="utf-8")
    assert "ABC-123" not in telemetry_text
    assert "email" not in telemetry_text.lower()
    assert "license_key" not in telemetry_text.lower()
    assert services["spx-server"]["image"] == SPX_SERVER_IMAGE
    assert services["spx-server"]["container_name"] == "spx-server"
    assert (
        services["spx-server"]["environment"]["SPX_TELEMETRY_ENVIRONMENT"] == "staging"
    )
    assert (
        services["spx-server"]["environment"]["SPX_TELEMETRY_MANIFEST_PATH"]
        == "/app/telemetry.json"
    )
    assert (
        "./telemetry.json:/app/telemetry.json:ro" in services["spx-server"]["volumes"]
    )
    transaction_services = yaml.safe_load(
        transaction_compose_path.read_text(encoding="utf-8")
    )["services"]
    transaction_server = next(
        service
        for name, service in transaction_services.items()
        if name.endswith("-spx-server")
    )
    transaction_knx = next(
        service
        for name, service in transaction_services.items()
        if name.endswith("-knx_gateway")
    )
    assert transaction_server["container_name"].startswith("spx-transaction-")
    assert (
        transaction_server["container_name"] != services["spx-server"]["container_name"]
    )
    assert "knx_gateway" in transaction_knx["networks"]["default"]["aliases"]
    assert (output_dir / "assets" / "knx" / "knxd.ini").is_file()
    assert "8000:8000" in services["spx-server"]["ports"]
    assert "healthcheck" in services["spx-server"]
    assert "host.docker.internal:host-gateway" in services["spx-server"].get(
        "extra_hosts", []
    )
    assert (
        "${SPX_BIND_MODBUS_TCP_GATEWAY:-127.0.0.1}:502:502"
        in services["spx-server"]["ports"]
    )
    assert (
        "${SPX_BIND_MQTT_BROKER:-127.0.0.1}:1883:1883"
        in services["mqtt_broker"]["ports"]
    )
    mqtt_volumes = services["mqtt_broker"].get("volumes", [])
    assert any(
        vol.startswith("./assets/mosquitto/mosquitto.conf") for vol in mqtt_volumes
    )

    env_path = output_dir / ".env"
    assert env_path.read_text(encoding="utf-8").splitlines() == [
        "SPX_PRODUCT_KEY=ABC-123",
        "SPX_BIND_MQTT_BROKER=127.0.0.1",
        "SPX_BIND_MODBUS_TCP_GATEWAY=127.0.0.1",
        "SPX_BIND_KNX_GATEWAY=127.0.0.1",
    ]

    asset_file = output_dir / "assets" / "mosquitto" / "mosquitto.conf"
    assert asset_file.exists()
    assert (output_dir / "extensions").exists()

    bundle = json.loads((output_dir / "bundle.json").read_text(encoding="utf-8"))
    assert "license_key" not in bundle
    assert bundle["server_version"] == "v1.0.0-rc.65"
    assert bundle["ui_version"] == "v1.0.0-rc.68"
    assert bundle["compose_project"] == "spx"
    assert {1883, 502, 3671, 6720, 8000}.issubset(set(bundle["required_ports"]))
    service_mappings = {
        mapping["key"]: mapping for mapping in bundle["service_port_mappings"]
    }
    assert service_mappings["mqtt_broker/tcp/1883"]["host_port"] == 1883
    assert service_mappings["knx_gateway/tcp/6720"]["container_port"] == 6720
    assert bundle["modbus_port_mappings"] == {
        "gateway_host_port": 502,
        "gateway_container_port": 502,
        "instance_host_port_start": 5020,
        "instance_host_port_end": 5120,
        "instance_container_port_start": 5020,
        "instance_port_count": 101,
    }
    assert bundle.get("services") == [
        "mqtt_broker",
        "modbus_tcp_gateway",
        "knx_gateway",
    ]
    assert len(bundle["models"]) == 1
    assert bundle["models"][0]["id"] == "sensor"
    assert bundle.get("instances") == [
        {"model_id": "sensor", "instance_key": "inst_001"}
    ]


    assert bundle.get("start_instances") == ["inst_001"]

    start_path = output_dir / "spx-start.sh"
    stop_path = output_dir / "spx-stop.sh"
    assert start_path.exists()
    assert stop_path.exists()
    runner_path = output_dir / "bootstrap_runner.py"
    runtime_path = output_dir / "runtime_bootstrap.py"
    macos_python_helper_path = output_dir / "macos_python_runtime.sh"
    assert runner_path.exists()
    assert (output_dir / "modbus_port_configurator.py").exists()
    assert runtime_path.exists()
    assert macos_python_helper_path.exists()
    start_content = start_path.read_text(encoding="utf-8")
    stop_content = stop_path.read_text(encoding="utf-8")
    assert "trap cleanup_on_failure ERR INT TERM" in start_content
    assert "down --remove-orphans" not in start_content
    assert "docker compose -p spx" in start_content
    assert "docker-compose.transaction.yml" in start_content
    assert "--final-name" in start_content
    assert "stack_manager.py" in start_content
    assert "wait-health" in start_content
    assert "--installation-id" in start_content
    assert "bootstrap_runner.py" in start_content
    assert "stack_manager.py" in stop_content
    assert "--installation-id" in stop_content
    assert "runtime_bootstrap.py" in start_content
    assert "macos_python_runtime.sh" in start_content
    assert "pip install --user" not in start_content
    assert 'SYSTEM_PYTHON_BIN="${SPX_SYSTEM_PYTHON_BIN:-}"' in start_content
    assert 'RUNTIME_PYTHON_BIN=""' in start_content
    assert "TRANSACTION_PREPARED=0" in start_content
    assert "TRANSACTION_PREPARED=1" in start_content
    assert 'if [ "$TRANSACTION_PREPARED" -eq 1 ]; then' in start_content
    assert "PREPARE_ARGS=(" in start_content
    assert 'modbus_port_configurator.py" stage' in start_content
    assert 'modbus_port_configurator.py" commit' in start_content
    assert 'PREPARE_ARGS+=("--ports" "$REQUIRED_PORTS")' in start_content
    assert 'required-tcp-ports' in start_content
    assert 'PREPARE_ARGS+=("--tcp-ports" "$REQUIRED_TCP_PORTS")' in start_content
    assert "__REQUIRED_PORTS__" not in start_content
    assert "ASSUME_ARGS" not in start_content
    assert "commit" in start_content
    stack_runner_path = output_dir / "stack_runner.py"
    assert stack_runner_path.exists()
    stack_runner_content = stack_runner_path.read_text(encoding="utf-8")
    start_ps_path = output_dir / "spx-start.ps1"
    stop_ps_path = output_dir / "spx-stop.ps1"
    assert start_ps_path.exists()
    assert stop_ps_path.exists()
    start_ps_content = start_ps_path.read_text(encoding="utf-8")
    stop_ps_content = stop_ps_path.read_text(encoding="utf-8")
    assert "stack_runner.py" in start_ps_content
    assert "SpxLauncher.exe" in start_ps_content
    assert "$Env:SPX_SYSTEM_PYTHON_BIN" in start_ps_content
    assert "py -3" in start_ps_content
    assert "stack_runner.py" in stop_ps_content
    assert "SpxLauncher.exe" in stop_ps_content
    assert "$Env:SPX_SYSTEM_PYTHON_BIN" in stop_ps_content
    assert "btvirt_adapter" in stack_runner_content
    assert "bootstrap_runner.py" in stack_runner_content
    assert "runtime_bootstrap.py" in stack_runner_content
    assert "modbus_port_configurator.py" in stack_runner_content
    assert '"required-tcp-ports"' in stack_runner_content
    assert 'tcp_ports=tcp_ports' in stack_runner_content
    assert "wait-health" in stack_runner_content
    assert '"--services"' in stack_runner_content
    assert '"--status"' in stack_runner_content
    assert "[spx-start] Running services:" in stack_runner_content
    assert "docker compose" not in stack_runner_content
    assert "pip install --user" not in stack_runner_content


def test_bundle_records_selected_opcua_tcp_host_mappings(tmp_path: Path) -> None:
    index = build_index()
    index.services["opcua_server"] = manifest.ServiceManifest(
        id="opcua_server",
        name="OPC UA Server",
        protocol="opcua",
        description="Built-in OPC UA endpoints",
        ports=[
            manifest.ServicePort(
                transport="tcp",
                host=61610,
                container=61610,
                purpose="OPC UA discovery / sample compatibility",
            )
        ],
        deployment=manifest.ServiceDeployment(runtime="builtin"),
    )
    selection = WizardSelection(
        packages=[],
        profiles=[],
        protocols=[],
        install_examples=False,
        install_spx_ui=False,
        offline_bundle=False,
        license_key="TEST-KEY",
        model_ids=[],
        service_ids=["opcua_server"],
        instances=[],
        start_instances=[],
    )

    DeploymentGenerator(index).generate(selection, tmp_path / "opcua")
    bundle = json.loads(
        (tmp_path / "opcua" / "bundle.json").read_text(encoding="utf-8")
    )

    assert bundle["service_port_mappings"] == [
        {
            "key": "opcua_server/tcp/61610",
            "service_id": "opcua_server",
            "service_name": "OPC UA Server",
            "purpose": "OPC UA discovery / sample compatibility",
            "compose_service": "spx-server",
            "transport": "tcp",
            "default_host_port": 61610,
            "host_port": 61610,
            "container_port": 61610,
        }
    ]


def test_generator_repairs_stale_directory_at_file_asset_path(tmp_path: Path) -> None:
    generator = DeploymentGenerator(build_index())
    selection = WizardSelection(
        packages=["pack_a"],
        profiles=[],
        protocols=[],
        install_examples=False,
        install_spx_ui=False,
        offline_bundle=False,
        license_key="ABC-123",
        model_ids=[],
        service_ids=["knx_gateway"],
        instances=[],
        start_instances=[],
    )
    output_dir = tmp_path / "out"
    generator.generate(selection, output_dir)

    asset = output_dir / "assets" / "knx" / "knxd.ini"
    source = generator.repo_root / "library/assets/knx/knxd.ini"
    assert asset.is_file()
    asset.unlink()
    asset.mkdir()
    shutil.copy2(source, asset / source.name)

    generator.generate(selection, output_dir)

    assert asset.is_file()
    assert asset.read_bytes() == source.read_bytes()
    transaction_services = yaml.safe_load(
        (output_dir / "docker-compose.transaction.yml").read_text(encoding="utf-8")
    )["services"]
    transaction_knx = next(
        service
        for name, service in transaction_services.items()
        if name.endswith("-knx_gateway")
    )
    assert "knx_gateway" in transaction_knx["networks"]["default"]["aliases"]


def test_generated_start_handles_empty_args_and_runtime_paths_with_spaces(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "Library" / "Application Support" / "SPX" / "generated"
    generator = DeploymentGenerator(build_index())
    selection = WizardSelection(
        packages=["pack_a"],
        profiles=[],
        protocols=[],
        install_examples=True,
        install_spx_ui=False,
        offline_bundle=False,
        license_key="KEY-SPACE",
        model_ids=["sensor"],
        service_ids=["mqtt_broker"],
        instances=[],
        start_instances=[],
    )
    generator.generate(selection, output_dir)

    runtime_python = (
        output_dir
        / "Library"
        / "Application Support"
        / "SPX"
        / "runtime"
        / "bin"
        / "python"
    )
    runtime_python.parent.mkdir(parents=True)
    runtime_python.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "-" ]; then exit 1; fi\n'
        'case "$1" in\n'
        '  *stack_manager.py) printf \'%s\\n\' "$2 $*" >> "$FAKE_RUNTIME_LOG"; exit 0 ;;\n'
        "  *bootstrap_runner.py) printf '%s\\n' bootstrap >> \"$FAKE_RUNTIME_LOG\"; exit 0 ;;\n"
        "esac\n"
        "exit 0\n",
        encoding="utf-8",
    )
    runtime_python.chmod(0o755)
    (output_dir / "runtime_bootstrap.py").write_text(
        "import os\n"
        "from pathlib import Path\n"
        "path = Path(os.environ['FAKE_RUNTIME_PYTHON'])\n"
        "print(path)\n",
        encoding="utf-8",
    )
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    (fake_bin / "docker").write_text(
        "#!/bin/sh\n"
        'case "$*" in\n'
        "  *\"ps --services --status running\"*) printf '%s\\n' transaction-test-spx-server ;;\n"
        "esac\n"
        "exit 0\n",
        encoding="utf-8",
    )
    (fake_bin / "docker").chmod(0o755)
    bash = shutil.which("bash")
    if os.name == "nt":
        bash = next(
            (
                str(candidate)
                for candidate in (
                    Path(r"C:\Program Files\Git\bin\bash.exe"),
                    Path(r"C:\Program Files\Git\usr\bin\bash.exe"),
                )
                if candidate.is_file()
            ),
            None,
        )
        if bash is None:
            pytest.skip(
                "A Bash executable is required to exercise the generated shell launcher"
            )
    system_python = tmp_path / "Library" / "Application Support" / "system-python"
    system_python.parent.mkdir(parents=True, exist_ok=True)
    python_executable = sys.executable
    if os.name == "nt":
        converted = subprocess.run(
            [bash, "-lc", 'cygpath -u "$1"', "_", sys.executable],
            capture_output=True,
            text=True,
            check=False,
        )
        assert converted.returncode == 0, converted.stderr
        python_executable = converted.stdout.strip()
    system_python.write_text(
        f"#!/bin/sh\nexec '{python_executable}' \"$@\"\n",
        encoding="utf-8",
    )
    system_python.chmod(0o755)
    log_path = tmp_path / "runtime.log"
    environment = {
        **os.environ,
        "PATH": f"{fake_bin}:/usr/bin:/bin",
        "FAKE_RUNTIME_PYTHON": str(runtime_python),
        "FAKE_RUNTIME_LOG": str(log_path),
        "SPX_SYSTEM_PYTHON_BIN": str(system_python),
        "PYTHON_BIN": str(
            tmp_path / "Library" / "Application Support" / "installer-python"
        ),
    }
    command_prefix = [bash] if bash else []

    first = subprocess.run(
        [*command_prefix, str(output_dir / "spx-start.sh")],
        cwd=output_dir,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    second = subprocess.run(
        [*command_prefix, str(output_dir / "spx-start.sh"), "--yes"],
        cwd=output_dir,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert "unbound variable" not in (
        first.stdout + first.stderr + second.stdout + second.stderr
    )
    log = log_path.read_text(encoding="utf-8")
    assert "prepare" in log
    assert "--yes" in log


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
    assert "command" not in ui_service
    assert ui_service["depends_on"]["spx-server"]["condition"] == "service_healthy"
    start_content = (output_dir / "spx-start.sh").read_text(encoding="utf-8")
    assert "ps --services --status running" in start_content
    assert 'grep -Fxq "$TRANSACTION_UI_SERVICE"' in start_content
    assert "[spx-start] Running services:" in start_content
    assert ' --env-file "$SCRIPT_DIR/.env" ps\n' not in start_content
    transaction_services = yaml.safe_load(
        (output_dir / "docker-compose.transaction.yml").read_text(encoding="utf-8")
    )["services"]
    assert any("__TRANSACTION_TOKEN__" in name for name in transaction_services)


def test_generator_bakes_production_telemetry_target_from_installer_marker(
    tmp_path: Path,
    monkeypatch,
) -> None:
    installer_root = tmp_path / "release-payload" / "installer"
    installer_root.mkdir(parents=True)
    (installer_root / "telemetry_environment.txt").write_text(
        "production\n", encoding="utf-8"
    )
    monkeypatch.setattr(
        "installer.generator.paths.repo_root",
        lambda: installer_root.parent,
    )
    generator = DeploymentGenerator(build_index())
    selection = WizardSelection(
        packages=["pack_a"],
        profiles=[],
        protocols=[],
        install_examples=False,
        install_spx_ui=False,
        offline_bundle=False,
        license_key="RELEASE-TEST-KEY",
        model_ids=[],
        service_ids=[],
        instances=[],
        start_instances=[],
    )

    output_dir = tmp_path / "production-output"
    generator.generate(selection, output_dir)

    compose = yaml.safe_load(
        (output_dir / "docker-compose.generated.yml").read_text(encoding="utf-8")
    )
    assert (
        compose["services"]["spx-server"]["environment"]["SPX_TELEMETRY_ENVIRONMENT"]
        == "production"
    )


def test_generator_uses_runtime_available_healthcheck(tmp_path: Path) -> None:
    index = build_index()
    generator = DeploymentGenerator(index)
    selection = WizardSelection(
        packages=["pack_a"],
        profiles=[],
        protocols=[],
        install_examples=False,
        install_spx_ui=False,
        offline_bundle=False,
        license_key="KEY-HEALTH",
        model_ids=[],
        service_ids=[],
        instances=[],
        start_instances=[],
    )

    output_dir = tmp_path / "out-health"
    generator.generate(selection, output_dir)

    server = yaml.safe_load(
        (output_dir / "docker-compose.generated.yml").read_text(encoding="utf-8")
    )["services"]["spx-server"]
    assert server["healthcheck"]["test"][0:3] == ["CMD", "python", "-c"]
    assert "/health" in server["healthcheck"]["test"][3]


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
    assert (
        "${BACNET_BIND_ADDR:-${SPX_BIND_BACNET_GATEWAY:-127.0.0.1}}:47808:47808/udp"
        in ports
    )
    assert (
        "${BACNET_BIND_ADDR:-${SPX_BIND_BACNET_GATEWAY:-127.0.0.1}}:47818:47818/udp"
        in ports
    )
    assert (
        "${BACNET_BIND_ADDR:-${SPX_BIND_BACNET_GATEWAY:-127.0.0.1}}:47828:47828/udp"
        in ports
    )


def test_generator_applies_per_service_bind_addresses(tmp_path: Path) -> None:
    index = build_index()
    generator = DeploymentGenerator(index)
    selection = WizardSelection(
        packages=["pack_a"],
        profiles=[],
        protocols=[],
        install_examples=True,
        install_spx_ui=True,
        offline_bundle=False,
        license_key="ABC-123",
        model_ids=["sensor"],
        service_ids=["mqtt_broker", "modbus_tcp_gateway", "bacnet_gateway"],
        instances=[],
        start_instances=[],
        service_bind_addresses={
            "mqtt_broker": "192.168.0.142",
            "modbus_tcp_gateway": "127.0.0.1",
            "bacnet_gateway": "10.0.0.15",
        },
    )

    output_dir = tmp_path / "out-bindings"
    generator.generate(selection, output_dir)
    compose = yaml.safe_load(
        (output_dir / "docker-compose.generated.yml").read_text(encoding="utf-8")
    )

    assert (
        "${SPX_BIND_MQTT_BROKER:-192.168.0.142}:1883:1883"
        in compose["services"]["mqtt_broker"]["ports"]
    )
    assert (
        "${SPX_BIND_MODBUS_TCP_GATEWAY:-127.0.0.1}:5020:5020"
        in compose["services"]["spx-server"]["ports"]
    )
    assert (
        "${BACNET_BIND_ADDR:-${SPX_BIND_BACNET_GATEWAY:-10.0.0.15}}:47808:47808/udp"
        in compose["services"]["spx-server"]["ports"]
    )
    assert (output_dir / "network.py").exists()
    env = (output_dir / ".env").read_text(encoding="utf-8")
    assert "SPX_BIND_MQTT_BROKER=192.168.0.142" in env
    start_sh = (output_dir / "spx-start.sh").read_text(encoding="utf-8")
    network_preflight = start_sh.index(
        '"$RUNTIME_PYTHON_BIN" "$SCRIPT_DIR/network.py" --env-file'
    )
    manager_preflight = start_sh.index(
        '"$RUNTIME_PYTHON_BIN" "$MANAGER"', network_preflight
    )
    transaction_prepare = start_sh.index("TRANSACTION_PREPARED=1")
    assert network_preflight < manager_preflight < transaction_prepare
    assert start_sh.index('modbus_port_configurator.py" stage') < network_preflight
    assert start_sh.index('required-tcp-ports') < manager_preflight
    assert start_sh.index('modbus_port_configurator.py" commit') > transaction_prepare
    stack_runner = (output_dir / "stack_runner.py").read_text(encoding="utf-8")
    network_preflight_python = stack_runner.index('stage = "preflight"')
    network_helper_python = stack_runner.index(
        'str(script_dir / "network.py")', network_preflight_python
    )
    manager_prepare_python = stack_runner.index('"prepare"', network_helper_python)
    transaction_prepare_python = stack_runner.index(
        "transaction_prepared = True", manager_prepare_python
    )
    assert (
        network_preflight_python
        < network_helper_python
        < manager_prepare_python
        < transaction_prepare_python
    )
    assert (
        stack_runner.index('"stage"', network_preflight_python) < network_helper_python
    )
    assert (
        stack_runner.index('"commit"', manager_prepare_python)
        > transaction_prepare_python
    )


def test_generator_writes_protocol_bundle_without_instances(tmp_path: Path) -> None:
    index = build_index()
    generator = DeploymentGenerator(index)
    selection = WizardSelection(
        packages=[],
        profiles=[],
        protocols=["mqtt"],
        install_examples=True,
        install_spx_ui=False,
        offline_bundle=False,
        license_key="PROTOCOL-KEY",
        model_ids=["sensor"],
        service_ids=["mqtt_broker"],
        instances=[],
        start_instances=[],
    )

    output_dir = tmp_path / "out-protocol"
    generator.generate(selection, output_dir)

    compose = yaml.safe_load(
        (output_dir / "docker-compose.generated.yml").read_text(encoding="utf-8")
    )
    services = compose["services"]
    assert set(services) == {"spx-server", "mqtt_broker"}

    bundle = json.loads((output_dir / "bundle.json").read_text(encoding="utf-8"))
    assert bundle["packages"] == []
    assert bundle["protocols"] == ["mqtt"]
    assert [entry["id"] for entry in bundle["models"]] == ["sensor"]
    assert bundle["instances"] == []
    assert bundle["start_instances"] == []
    assert bundle["services"] == ["mqtt_broker"]


def test_generator_writes_service_only_protocol_bundle(tmp_path: Path) -> None:
    index = build_index()
    generator = DeploymentGenerator(index)
    selection = WizardSelection(
        packages=[],
        profiles=[],
        protocols=["mqtt"],
        install_examples=False,
        install_spx_ui=False,
        offline_bundle=False,
        license_key="SERVICE-KEY",
        model_ids=[],
        service_ids=["mqtt_broker"],
        instances=[],
        start_instances=[],
    )

    output_dir = tmp_path / "out-service-only"
    generator.generate(selection, output_dir)

    compose = yaml.safe_load(
        (output_dir / "docker-compose.generated.yml").read_text(encoding="utf-8")
    )
    assert set(compose["services"]) == {"spx-server", "mqtt_broker"}

    bundle = json.loads((output_dir / "bundle.json").read_text(encoding="utf-8"))
    assert bundle["models"] == []
    assert bundle["instances"] == []
    assert bundle["start_instances"] == []
    assert bundle["services"] == ["mqtt_broker"]
