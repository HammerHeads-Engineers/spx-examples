from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from installer.modbus_port_configurator import (
    PortConfigurationCancelled,
    PortConfigurationError,
    PortSettings,
    _commit_stage,
    main,
    _ports_from_compose,
    _with_settings,
    stage_configuration,
)
from installer.stack_manager import PreflightResult


def _compose(*, transaction: bool = False) -> dict:
    service_name = "transaction-token-spx-server" if transaction else "spx-server"
    container_name = "spx-transaction-token-spx-server" if transaction else "spx-server"
    return {
        "name": "spx",
        "services": {
            service_name: {
                "container_name": container_name,
                "ports": [
                    "${SPX_BIND_MODBUS_TCP_GATEWAY:-127.0.0.1}:502:502",
                    *[
                        f"${{SPX_BIND_MODBUS_TCP_GATEWAY:-127.0.0.1}}:{port}:{port}"
                        for port in range(5020, 5121)
                    ],
                    "127.0.0.1:8000:8000",
                ],
            }
        },
    }


def _bundle() -> dict:
    return {
        "services": ["modbus_tcp_gateway"],
        "compose_project": "spx",
        "installation_id": "installation-1",
        "required_ports": [502, *range(5020, 5121), 8000],
        "modbus_port_mappings": {
            "gateway_host_port": 502,
            "gateway_container_port": 502,
            "instance_host_port_start": 5020,
            "instance_host_port_end": 5120,
            "instance_container_port_start": 5020,
            "instance_port_count": 101,
        },
    }


class FakeManager:
    def __init__(self, occupied: dict[int, list[str]]) -> None:
        self.occupied = occupied
        self.checked: list[list[int]] = []

    def preflight(self, required_ports: list[int]) -> PreflightResult:
        self.checked.append(list(required_ports))
        return PreflightResult(
            occupied_ports=self.occupied,
            required_ports=list(required_ports),
        )


def test_default_modbus_mapping_keeps_internal_and_host_ports_aligned() -> None:
    compose = _compose()
    remapped = _with_settings(compose, PortSettings())
    ports = remapped["services"]["spx-server"]["ports"]

    assert "${SPX_BIND_MODBUS_TCP_GATEWAY:-127.0.0.1}:502:502" in ports
    assert "${SPX_BIND_MODBUS_TCP_GATEWAY:-127.0.0.1}:5020:5020" in ports
    assert "${SPX_BIND_MODBUS_TCP_GATEWAY:-127.0.0.1}:5120:5120" in ports
    assert _ports_from_compose(remapped) == [502, *range(5020, 5121), 8000]


def test_conflicts_suggest_next_free_gateway_and_instance_range() -> None:
    manager = FakeManager(
        {
            502: ["process ModbusService (PID 17)"],
            5040: ["process CDPSvc (PID 18)"],
            1502: ["process other (PID 19)"],
            15020: ["process other (PID 20)"],
        }
    )
    answers = iter(["", ""])
    messages: list[str] = []
    settings, ports = stage_configuration_for_test(
        manager,
        input_fn=lambda _prompt: next(answers),
        output=messages.append,
    )

    assert settings == PortSettings(1503, 15021)
    assert 1503 in ports and 15021 in ports and 15121 in ports
    assert len(manager.checked) == 2
    assert any("CDPSvc" in message for message in messages)
    assert any("5040: process CDPSvc (PID 18)" in message for message in messages)
    assert any("1503" in message for message in messages)
    assert any("15021-15121" in message for message in messages)


def test_user_can_choose_custom_gateway_port_and_range_start() -> None:
    manager = FakeManager({502: ["process gateway"], 5040: ["process CDPSvc"]})
    answers = iter(["1602", "16020"])
    settings, _ = stage_configuration_for_test(
        manager,
        input_fn=lambda _prompt: next(answers),
        output=lambda _message: None,
    )

    assert settings == PortSettings(1602, 16020)
    remapped = _with_settings(_compose(), settings)
    ports = remapped["services"]["spx-server"]["ports"]
    assert "${SPX_BIND_MODBUS_TCP_GATEWAY:-127.0.0.1}:1602:502" in ports
    assert "${SPX_BIND_MODBUS_TCP_GATEWAY:-127.0.0.1}:16020:5020" in ports
    assert "${SPX_BIND_MODBUS_TCP_GATEWAY:-127.0.0.1}:16120:5120" in ports


def test_suggestions_start_at_the_documented_alternate_mappings() -> None:
    bundle = _bundle()
    bundle["modbus_port_mappings"]["gateway_host_port"] = 1602
    bundle["modbus_port_mappings"]["instance_host_port_start"] = 16020
    compose = _with_settings(_compose(), PortSettings(1602, 16020))
    manager = FakeManager({1602: ["process gateway"], 16050: ["process CDPSvc"]})
    answers = iter(["", ""])
    messages: list[str] = []

    settings, _ = stage_settings_for_case(
        bundle,
        compose,
        manager,
        input_fn=lambda _prompt: next(answers),
        output=messages.append,
    )

    assert settings == PortSettings(1502, 15020)
    assert any("Suggested mapping: 1502" in message for message in messages)
    assert any("Suggested mapping: 15020-15120" in message for message in messages)


def test_custom_choice_overlapping_another_required_port_is_reprompted() -> None:
    manager = FakeManager({502: ["process gateway"], 5040: ["process CDPSvc"]})
    answers = iter(["8000", "", ""])
    messages: list[str] = []
    settings, _ = stage_configuration_for_test(
        manager,
        input_fn=lambda _prompt: next(answers),
        output=messages.append,
    )

    assert settings == PortSettings(1502, 15020)
    assert any(
        "overlaps occupied or already assigned" in message for message in messages
    )


def test_existing_range_overlap_with_selected_service_is_remapped() -> None:
    bundle = _bundle()
    bundle["modbus_port_mappings"]["instance_host_port_start"] = 15020
    bundle["modbus_port_mappings"]["instance_host_port_end"] = 15120
    compose = _with_settings(_compose(), PortSettings(502, 15020))
    compose["services"]["mqtt_broker"] = {"ports": ["127.0.0.1:15025:1883"]}
    manager = FakeManager({})

    settings, _ = stage_settings_for_case(
        bundle,
        compose,
        manager,
        input_fn=lambda _prompt: "",
        output=lambda _message: None,
    )

    assert settings == PortSettings(502, 15026)


def test_cancel_does_not_write_a_staged_or_persistent_mapping(tmp_path: Path) -> None:
    compose_file, bundle_file, env_file, transaction_file = _write_bundle_files(
        tmp_path
    )
    staged_file = tmp_path / "pending.json"
    before = {
        path: path.read_bytes()
        for path in (compose_file, bundle_file, transaction_file)
    }

    with pytest.raises(PortConfigurationCancelled):
        stage_configuration(
            compose_file=compose_file,
            bundle_file=bundle_file,
            env_file=env_file,
            staged_file=staged_file,
            input_fn=lambda _prompt: "Q",
            output=lambda _message: None,
            manager=FakeManager({5040: ["process CDPSvc"]}),
        )

    assert not staged_file.exists()
    assert {path: path.read_bytes() for path in before} == before


def test_noninteractive_conflict_fails_without_writing_mapping(
    tmp_path: Path,
) -> None:
    compose_file, bundle_file, env_file, transaction_file = _write_bundle_files(
        tmp_path
    )
    staged_file = tmp_path / "pending.json"
    before = {
        path: path.read_bytes()
        for path in (compose_file, bundle_file, transaction_file)
    }

    with pytest.raises(PortConfigurationError, match="Run spx-start interactively"):
        stage_configuration(
            compose_file=compose_file,
            bundle_file=bundle_file,
            env_file=env_file,
            staged_file=staged_file,
            output=lambda _message: None,
            manager=FakeManager({5040: ["process CDPSvc"]}),
        )

    assert not staged_file.exists()
    assert {path: path.read_bytes() for path in before} == before


def test_commit_updates_compose_transaction_template_and_required_ports(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    compose_file, bundle_file, env_file, transaction_file = _write_bundle_files(
        tmp_path
    )
    staged_file = tmp_path / "pending.json"
    stage_configuration(
        compose_file=compose_file,
        bundle_file=bundle_file,
        env_file=env_file,
        staged_file=staged_file,
        input_fn=lambda _prompt: "",
        output=lambda _message: None,
        manager=FakeManager({502: ["process gateway"], 5040: ["process CDPSvc"]}),
    )

    updated = _commit_stage(
        compose_file=compose_file,
        transaction_template=transaction_file,
        bundle_file=bundle_file,
        staged_file=staged_file,
    )
    compose_server = yaml.safe_load(compose_file.read_text(encoding="utf-8"))[
        "services"
    ]["spx-server"]
    transaction_server = next(
        service
        for name, service in yaml.safe_load(
            transaction_file.read_text(encoding="utf-8")
        )["services"].items()
        if name.endswith("spx-server")
    )

    assert (
        "${SPX_BIND_MODBUS_TCP_GATEWAY:-127.0.0.1}:1502:502" in compose_server["ports"]
    )
    assert (
        "${SPX_BIND_MODBUS_TCP_GATEWAY:-127.0.0.1}:15020:5020"
        in compose_server["ports"]
    )
    assert (
        "${SPX_BIND_MODBUS_TCP_GATEWAY:-127.0.0.1}:15120:5120"
        in compose_server["ports"]
    )
    assert (
        "${SPX_BIND_MODBUS_TCP_GATEWAY:-127.0.0.1}:15020:5020"
        in transaction_server["ports"]
    )
    assert updated["modbus_port_mappings"]["gateway_host_port"] == 1502
    assert updated["modbus_port_mappings"]["instance_host_port_start"] == 15020
    assert updated["required_ports"] == [1502, 8000, *range(15020, 15121)]
    assert (
        json.loads(bundle_file.read_text(encoding="utf-8"))["required_ports"]
        == updated["required_ports"]
    )
    assert (
        main(
            [
                "summary",
                "--bundle",
                str(bundle_file),
                "--compose-file",
                str(compose_file),
            ]
        )
        == 0
    )
    assert "Connect Modbus clients to host port 1502" in capsys.readouterr().out

    next_stage = tmp_path / "next-pending.json"
    persisted = stage_configuration(
        compose_file=compose_file,
        bundle_file=bundle_file,
        env_file=env_file,
        staged_file=next_stage,
        output=lambda _message: None,
        manager=FakeManager({}),
    )
    assert persisted["changed"] is False
    assert persisted["gateway_host_port"] == 1502
    assert persisted["instance_host_start"] == 15020


def stage_configuration_for_test(
    manager: FakeManager,
    *,
    input_fn,
    output,
) -> tuple[PortSettings, list[int]]:
    from installer.modbus_port_configurator import _stage_settings

    bundle = _bundle()
    compose = _compose()
    return _stage_settings(bundle, compose, manager, input_fn=input_fn, output=output)


def stage_settings_for_case(bundle, compose, manager, *, input_fn, output):
    from installer.modbus_port_configurator import _stage_settings

    return _stage_settings(bundle, compose, manager, input_fn=input_fn, output=output)


def _write_bundle_files(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    compose_file = tmp_path / "docker-compose.generated.yml"
    bundle_file = tmp_path / "bundle.json"
    env_file = tmp_path / ".env"
    transaction_file = tmp_path / "docker-compose.transaction.yml"
    compose_file.write_text(
        yaml.safe_dump(_compose(), sort_keys=False), encoding="utf-8"
    )
    bundle_file.write_text(json.dumps(_bundle(), indent=2), encoding="utf-8")
    env_file.write_text("SPX_PRODUCT_KEY=REDACTED\n", encoding="utf-8")
    transaction_file.write_text(
        yaml.safe_dump(_compose(transaction=True), sort_keys=False),
        encoding="utf-8",
    )
    return compose_file, bundle_file, env_file, transaction_file
