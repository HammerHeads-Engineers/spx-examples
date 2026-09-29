# SPDX-License-Identifier: MIT
"""Choose and persist host-side Modbus port mappings for generated stacks."""

from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

import yaml

try:  # Support both package imports in tests and direct execution in bundles.
    from .stack_manager import StackManager, StackManagerError
except ImportError:  # pragma: no cover - exercised by generated launchers
    from stack_manager import StackManager, StackManagerError


GATEWAY_CONTAINER_PORT = 502
INSTANCE_CONTAINER_START = 5020
INSTANCE_PORT_COUNT = 101
GATEWAY_SUGGESTION_START = 1502
INSTANCE_SUGGESTION_START = 15020

_PORT_BINDING = re.compile(
    r"^(?P<prefix>.*:)(?P<host>\d+):(?P<container>\d+)" r"(?P<suffix>/(?:tcp|udp))?$"
)


class PortConfigurationError(RuntimeError):
    """The requested Modbus port mapping cannot be configured safely."""


class PortConfigurationCancelled(PortConfigurationError):
    """The user cancelled the port selection."""


@dataclass(frozen=True)
class PortSettings:
    gateway_host_port: int = GATEWAY_CONTAINER_PORT
    instance_host_start: int = INSTANCE_CONTAINER_START

    @property
    def instance_host_end(self) -> int:
        return self.instance_host_start + INSTANCE_PORT_COUNT - 1

    @property
    def published_ports(self) -> set[int]:
        return {
            self.gateway_host_port,
            *range(self.instance_host_start, self.instance_host_end + 1),
        }


def _read_yaml(path: Path) -> dict:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise PortConfigurationError(f"Could not read {path.name}: {exc}") from exc
    if not isinstance(value, dict):
        raise PortConfigurationError(f"{path.name} must contain a YAML object")
    return value


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PortConfigurationError(f"Could not read {path.name}: {exc}") from exc
    if not isinstance(value, dict):
        raise PortConfigurationError(f"{path.name} must contain a JSON object")
    return value


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _binding_parts(raw: object) -> tuple[str, int, int, str] | None:
    match = _PORT_BINDING.match(str(raw))
    if not match:
        return None
    return (
        match.group("prefix"),
        int(match.group("host")),
        int(match.group("container")),
        match.group("suffix") or "",
    )


def _is_tcp(suffix: str) -> bool:
    return suffix in {"", "/tcp"}


def _spx_server(compose: dict) -> dict | None:
    services = compose.get("services")
    if not isinstance(services, dict):
        return None
    for name, service in services.items():
        if not isinstance(service, dict):
            continue
        container_name = str(service.get("container_name", ""))
        if name == "spx-server" or container_name.endswith("spx-server"):
            return service
    return None


def _modbus_selected(bundle: dict) -> bool:
    services = bundle.get("services", [])
    return isinstance(services, list) and "modbus_tcp_gateway" in services


def _stored_settings(bundle: dict, compose: dict) -> PortSettings:
    stored = bundle.get("modbus_port_mappings")
    if isinstance(stored, dict):
        try:
            return validate_settings(
                PortSettings(
                    gateway_host_port=int(stored.get("gateway_host_port", 502)),
                    instance_host_start=int(
                        stored.get("instance_host_port_start", 5020)
                    ),
                )
            )
        except (TypeError, ValueError, PortConfigurationError):
            pass

    server = _spx_server(compose) or {}
    gateway = GATEWAY_CONTAINER_PORT
    instance_start = INSTANCE_CONTAINER_START
    for entry in server.get("ports", []) or []:
        parts = _binding_parts(entry)
        if parts is None:
            continue
        _, host, container, suffix = parts
        if not _is_tcp(suffix):
            continue
        if container == GATEWAY_CONTAINER_PORT:
            gateway = host
        elif (
            INSTANCE_CONTAINER_START
            <= container
            < INSTANCE_CONTAINER_START + INSTANCE_PORT_COUNT
        ):
            instance_start = host - (container - INSTANCE_CONTAINER_START)
    return validate_settings(PortSettings(gateway, instance_start))


def validate_settings(settings: PortSettings) -> PortSettings:
    gateway = int(settings.gateway_host_port)
    start = int(settings.instance_host_start)
    end = start + INSTANCE_PORT_COUNT - 1
    if not 1 <= gateway <= 65535:
        raise PortConfigurationError(
            "The Modbus gateway host port must be from 1 to 65535"
        )
    if not 1 <= start <= 65535 or end > 65535:
        raise PortConfigurationError(
            f"The Modbus instance range must fit within ports 1-65535 "
            f"({INSTANCE_PORT_COUNT} consecutive ports)"
        )
    if start <= gateway <= end:
        raise PortConfigurationError(
            "The gateway port cannot overlap the instance port range"
        )
    return PortSettings(gateway, start)


def _ports_from_compose(compose: dict) -> list[int]:
    ports: set[int] = set()
    services = compose.get("services", {})
    if not isinstance(services, dict):
        return []
    for service in services.values():
        if not isinstance(service, dict):
            continue
        for entry in service.get("ports", []) or []:
            parts = _binding_parts(entry)
            if parts is not None:
                ports.add(parts[1])
    return sorted(ports)


def _fixed_host_owners(compose: dict) -> dict[int, list[str]]:
    owners: dict[int, list[str]] = {}
    services = compose.get("services", {})
    server = _spx_server(compose)
    if not isinstance(services, dict):
        return owners
    for service_name, service in services.items():
        if not isinstance(service, dict):
            continue
        is_server = service is server
        for entry in service.get("ports", []) or []:
            parts = _binding_parts(entry)
            if parts is None:
                continue
            _, host, container, suffix = parts
            is_modbus_mapping = (
                is_server
                and _is_tcp(suffix)
                and (
                    container == GATEWAY_CONTAINER_PORT
                    or INSTANCE_CONTAINER_START
                    <= container
                    < INSTANCE_CONTAINER_START + INSTANCE_PORT_COUNT
                )
            )
            if is_modbus_mapping:
                continue
            label = f"selected service {service_name}"
            values = owners.setdefault(host, [])
            if label not in values:
                values.append(label)
    return owners


def _with_settings(compose: dict, settings: PortSettings) -> dict:
    result = json.loads(json.dumps(compose))
    server = _spx_server(result)
    if server is None:
        raise PortConfigurationError(
            "Generated Compose configuration has no SPX server service"
        )
    found_gateway = False
    found_instance_targets: set[int] = set()
    remapped: list[str] = []
    for entry in server.get("ports", []) or []:
        parts = _binding_parts(entry)
        if parts is None:
            remapped.append(str(entry))
            continue
        prefix, _, container, suffix = parts
        host = None
        if _is_tcp(suffix) and container == GATEWAY_CONTAINER_PORT:
            host = settings.gateway_host_port
            found_gateway = True
        elif (
            _is_tcp(suffix)
            and INSTANCE_CONTAINER_START
            <= container
            < INSTANCE_CONTAINER_START + INSTANCE_PORT_COUNT
        ):
            host = settings.instance_host_start + container - INSTANCE_CONTAINER_START
            found_instance_targets.add(container)
        if host is None:
            remapped.append(str(entry))
        else:
            remapped.append(f"{prefix}{host}:{container}{suffix}")
    if not found_gateway:
        raise PortConfigurationError(
            "The Modbus gateway port mapping (container port 502/TCP) is missing"
        )
    expected_targets = set(
        range(INSTANCE_CONTAINER_START, INSTANCE_CONTAINER_START + INSTANCE_PORT_COUNT)
    )
    if found_instance_targets != expected_targets:
        raise PortConfigurationError(
            "The generated Modbus instance mapping must expose container ports 5020-5120/TCP"
        )
    server["ports"] = remapped
    return result


def _owner_text(owners: Iterable[str]) -> str:
    values = list(owners)
    return ", ".join(values) if values else "another process"


def _first_available_port(start: int, unavailable: set[int]) -> int | None:
    for port in range(max(1, start), 65536):
        if port not in unavailable:
            return port
    return None


def _first_available_range(start: int, unavailable: set[int]) -> int | None:
    candidate = max(1, start)
    last_start = 65536 - INSTANCE_PORT_COUNT
    while candidate <= last_start:
        collision = next(
            (
                port
                for port in range(candidate, candidate + INSTANCE_PORT_COUNT)
                if port in unavailable
            ),
            None,
        )
        if collision is None:
            return candidate
        candidate = collision + 1
    return None


def _interactive(
    input_fn: Callable[[str], str] | None,
) -> tuple[bool, Callable[[str], str]]:
    if input_fn is not None:
        return True, input_fn
    try:
        can_prompt = sys.stdin is not None and sys.stdin.isatty()
    except (AttributeError, OSError):
        can_prompt = False
    return can_prompt, input


def _ask_mapping(
    *,
    label: str,
    current: int,
    suggestion: int,
    is_range: bool,
    conflicts: dict[int, list[str]],
    unavailable: set[int],
    input_fn: Callable[[str], str],
    output: Callable[[str], None],
) -> int:
    width = INSTANCE_PORT_COUNT - 1 if is_range else 0
    current_text = f"{current}-{current + width}" if is_range else str(current)
    suggested_text = (
        f"{suggestion}-{suggestion + width}" if is_range else str(suggestion)
    )
    conflict_text = "; ".join(
        f"{port}: {_owner_text(owners)}" for port, owners in sorted(conflicts.items())
    )
    while True:
        output(
            f"[spx-preflight] Modbus {label} host mapping {current_text} has conflict(s): "
            f"{conflict_text}. Suggested mapping: {suggested_text}."
        )
        try:
            answer = input_fn(
                f"[spx-preflight] Press Enter to use {suggested_text}, enter a new "
                f"{'range start' if is_range else 'port'}, or type Q to quit: "
            ).strip()
        except EOFError as exc:
            raise PortConfigurationCancelled(
                "No terminal input is available to choose an alternate Modbus port mapping. "
                "Run spx-start interactively."
            ) from exc
        if answer.lower() == "q":
            raise PortConfigurationCancelled(
                "Port selection cancelled; no Modbus mapping was changed."
            )
        if not answer:
            return suggestion
        try:
            choice = int(answer)
        except ValueError:
            output("[spx-preflight] Enter a port number or Q to quit.")
            continue
        try:
            validate_settings(
                PortSettings(
                    gateway_host_port=(
                        choice if not is_range else GATEWAY_CONTAINER_PORT
                    ),
                    instance_host_start=(
                        choice if is_range else INSTANCE_CONTAINER_START
                    ),
                )
            )
        except PortConfigurationError as exc:
            output(f"[spx-preflight] {exc}.")
            continue
        candidate_ports = (
            set(range(choice, choice + INSTANCE_PORT_COUNT)) if is_range else {choice}
        )
        collisions = sorted(candidate_ports & unavailable)
        if collisions:
            sample = ", ".join(str(port) for port in collisions[:5])
            output(
                f"[spx-preflight] That mapping overlaps occupied or already assigned "
                f"host port(s): {sample}. Choose another value."
            )
            continue
        return choice


def _stage_settings(
    bundle: dict,
    compose: dict,
    manager: StackManager,
    *,
    input_fn: Callable[[str], str] | None = None,
    output: Callable[[str], None] = print,
) -> tuple[PortSettings, list[int]]:
    if not _modbus_selected(bundle):
        return PortSettings(), _ports_from_compose(compose)

    current = _stored_settings(bundle, compose)
    can_prompt, prompt = _interactive(input_fn)
    while True:
        effective_compose = _with_settings(compose, current)
        required = _ports_from_compose(effective_compose)
        result = manager.preflight(required)
        conflicts = dict(result.unrelated_conflicts)
        fixed_owners = _fixed_host_owners(compose)
        for port, owners in fixed_owners.items():
            if port in current.published_ports:
                conflicts.setdefault(port, owners)
        gateway_conflict = current.gateway_host_port in conflicts
        instance_conflicts = sorted(
            set(range(current.instance_host_start, current.instance_host_end + 1))
            & set(conflicts)
        )
        if not gateway_conflict and not instance_conflicts:
            return current, required
        if not can_prompt:
            details = "; ".join(
                f"{port}: {_owner_text(conflicts[port])}"
                for port in sorted(
                    ({current.gateway_host_port} if gateway_conflict else set())
                    | set(instance_conflicts)
                )
            )
            raise PortConfigurationError(
                "Modbus TCP host ports are occupied ("
                f"{details}). Run spx-start interactively to select an alternate mapping."
            )

        fixed_owners = _fixed_host_owners(compose)
        fixed_ports = set(fixed_owners)
        occupied = set(result.occupied_ports)

        if gateway_conflict:
            unavailable = (
                occupied
                | fixed_ports
                | set(range(current.instance_host_start, current.instance_host_end + 1))
            )
            suggestion = _first_available_port(
                GATEWAY_SUGGESTION_START,
                unavailable,
            )
            if suggestion is None:
                raise PortConfigurationError(
                    "No free host port is available for the Modbus gateway"
                )
            current = PortSettings(
                gateway_host_port=_ask_mapping(
                    label="gateway",
                    current=current.gateway_host_port,
                    suggestion=suggestion,
                    is_range=False,
                    conflicts={
                        current.gateway_host_port: conflicts[current.gateway_host_port]
                    },
                    unavailable=unavailable,
                    input_fn=prompt,
                    output=output,
                ),
                instance_host_start=current.instance_host_start,
            )

        if instance_conflicts:
            unavailable = occupied | fixed_ports | {current.gateway_host_port}
            suggestion = _first_available_range(
                INSTANCE_SUGGESTION_START,
                unavailable,
            )
            if suggestion is None:
                raise PortConfigurationError(
                    "No free contiguous host range is available for Modbus instances"
                )
            current = PortSettings(
                gateway_host_port=current.gateway_host_port,
                instance_host_start=_ask_mapping(
                    label="instance range",
                    current=current.instance_host_start,
                    suggestion=suggestion,
                    is_range=True,
                    conflicts={port: conflicts[port] for port in instance_conflicts},
                    unavailable=unavailable,
                    input_fn=prompt,
                    output=output,
                ),
            )
        current = validate_settings(current)


def stage_configuration(
    *,
    compose_file: Path,
    bundle_file: Path,
    env_file: Path,
    staged_file: Path,
    input_fn: Callable[[str], str] | None = None,
    output: Callable[[str], None] = print,
    manager: StackManager | None = None,
) -> dict:
    compose = _read_yaml(compose_file)
    bundle = _read_json(bundle_file)
    settings = _stored_settings(bundle, compose)
    selected_manager = manager or StackManager(
        compose_file,
        env_file,
        project=str(bundle.get("compose_project") or "spx"),
        installation_id=str(bundle.get("installation_id") or ""),
    )
    settings, ports = _stage_settings(
        bundle,
        compose,
        selected_manager,
        input_fn=input_fn,
        output=output,
    )
    staged = {
        "modbus_selected": _modbus_selected(bundle),
        "changed": settings != _stored_settings(bundle, compose),
        "gateway_host_port": settings.gateway_host_port,
        "instance_host_start": settings.instance_host_start,
        "required_ports": ports,
    }
    _write_json(staged_file, staged)
    return staged


def _serialized_compose(compose: dict) -> str:
    return yaml.safe_dump(compose, sort_keys=False, allow_unicode=True)


def _commit_stage(
    *,
    compose_file: Path,
    transaction_template: Path,
    bundle_file: Path,
    staged_file: Path,
) -> dict:
    staged = _read_json(staged_file)
    bundle = _read_json(bundle_file)
    if not staged.get("modbus_selected") or not staged.get("changed"):
        return bundle

    settings = validate_settings(
        PortSettings(
            gateway_host_port=int(staged["gateway_host_port"]),
            instance_host_start=int(staged["instance_host_start"]),
        )
    )
    compose = _with_settings(_read_yaml(compose_file), settings)
    transaction = _with_settings(_read_yaml(transaction_template), settings)
    bundle["modbus_port_mappings"] = {
        "gateway_host_port": settings.gateway_host_port,
        "gateway_container_port": GATEWAY_CONTAINER_PORT,
        "instance_host_port_start": settings.instance_host_start,
        "instance_host_port_end": settings.instance_host_end,
        "instance_container_port_start": INSTANCE_CONTAINER_START,
        "instance_port_count": INSTANCE_PORT_COUNT,
    }
    bundle["required_ports"] = _ports_from_compose(compose)

    updates = {
        compose_file: _serialized_compose(compose),
        transaction_template: _serialized_compose(transaction),
        bundle_file: json.dumps(bundle, indent=2) + "\n",
    }
    originals: dict[Path, bytes] = {}
    temporary: dict[Path, Path] = {}
    replaced: list[Path] = []
    try:
        for path, contents in updates.items():
            originals[path] = path.read_bytes()
            temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
            temporary[path] = temp_path
            temp_path.write_text(contents, encoding="utf-8")
        for path, temp_path in temporary.items():
            temp_path.replace(path)
            replaced.append(path)
    except OSError as exc:
        for path in reversed(replaced):
            try:
                path.write_bytes(originals[path])
            except OSError:
                pass
        raise PortConfigurationError(
            f"Could not persist the Modbus port mapping: {exc}"
        ) from exc
    finally:
        for temp_path in temporary.values():
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
    return bundle


def _print_required_ports(staged_file: Path) -> int:
    staged = _read_json(staged_file)
    print(",".join(str(int(port)) for port in staged.get("required_ports", [])))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    stage_parser = subparsers.add_parser("stage")
    stage_parser.add_argument("--compose-file", type=Path, required=True)
    stage_parser.add_argument("--bundle", type=Path, required=True)
    stage_parser.add_argument("--env-file", type=Path, required=True)
    stage_parser.add_argument("--staged-file", type=Path, required=True)
    commit_parser = subparsers.add_parser("commit")
    commit_parser.add_argument("--compose-file", type=Path, required=True)
    commit_parser.add_argument("--transaction-template", type=Path, required=True)
    commit_parser.add_argument("--bundle", type=Path, required=True)
    commit_parser.add_argument("--staged-file", type=Path, required=True)
    ports_parser = subparsers.add_parser("required-ports")
    ports_parser.add_argument("--staged-file", type=Path, required=True)
    summary_parser = subparsers.add_parser("summary")
    summary_parser.add_argument("--bundle", type=Path, required=True)
    summary_parser.add_argument("--compose-file", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "stage":
            stage_configuration(
                compose_file=args.compose_file,
                bundle_file=args.bundle,
                env_file=args.env_file,
                staged_file=args.staged_file,
            )
        elif args.command == "commit":
            _commit_stage(
                compose_file=args.compose_file,
                transaction_template=args.transaction_template,
                bundle_file=args.bundle,
                staged_file=args.staged_file,
            )
        elif args.command == "required-ports":
            return _print_required_ports(args.staged_file)
        elif args.command == "summary":
            bundle = _read_json(args.bundle)
            if _modbus_selected(bundle):
                settings = _stored_settings(bundle, _read_yaml(args.compose_file))
                print(
                    f"[spx-start] Modbus TCP gateway: host port {settings.gateway_host_port} "
                    f"-> container port {GATEWAY_CONTAINER_PORT}/TCP"
                )
                if settings.gateway_host_port != GATEWAY_CONTAINER_PORT:
                    print(
                        "[spx-start] Connect Modbus clients to host port "
                        f"{settings.gateway_host_port}."
                    )
                print(
                    f"[spx-start] Modbus instance ports: host {settings.instance_host_start}-"
                    f"{settings.instance_host_end} -> container {INSTANCE_CONTAINER_START}-"
                    f"{INSTANCE_CONTAINER_START + INSTANCE_PORT_COUNT - 1}/TCP"
                )
        return 0
    except (PortConfigurationError, StackManagerError, OSError) as exc:
        print(f"[spx-preflight] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
