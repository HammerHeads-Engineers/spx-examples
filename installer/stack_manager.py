# SPDX-License-Identifier: MIT
"""Safety and transaction helpers for installer-managed Docker stacks.

The installer deliberately does not use ``compose down --remove-orphans``.
That command has too wide a blast radius for a machine that may contain more
than one Compose project.  This module first identifies the exact containers
that belong to SPX, snapshots their names, and only then operates on those
container IDs.

The file is also copied into generated bundles, so it intentionally uses only
the Python standard library.
"""

from __future__ import annotations

import argparse
from http.client import HTTPConnection, HTTPException
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

if __package__:
    from .product_key import runtime_product_key, validate_product_key_format
else:
    from product_key import runtime_product_key, validate_product_key_format


PROJECT = "spx"
LABEL_STACK = "com.simplephysx.spx.stack"
LABEL_MANAGED_BY = "com.simplephysx.spx.managed-by"
LABEL_PROJECT = "com.simplephysx.spx.project"
LABEL_INSTALLATION_ID = "com.simplephysx.spx.installation-id"

EXPECTED_IMAGES = {
    "spx-server": ("simplephysx/spx-server", "spx-server"),
    "spx-ui-server": ("simplephysx/spx-ui", "spx-ui-server"),
    "mosquitto-server": ("eclipse-mosquitto", "mosquitto"),
}
SNAPSHOT_PREFIXES = ("spx-snapshot-", "spx-rollback-")

_SECRET_PATTERNS = (
    re.compile(r"(?i)(spx[_-]?product[_-]?key\s*[=:]\s*)[^\s,;]+"),
    re.compile(r"(?i)(--product-key\s+)[^\s]+"),
    re.compile(r"(?i)(x-spx-product-key\s*:\s*)[^\s]+"),
)


class StackManagerError(RuntimeError):
    """Base error for a safe stack operation."""


class UserDeclined(StackManagerError):
    """Raised when an existing stack was not approved for replacement."""


class PreflightError(StackManagerError):
    """Raised when Docker or the requested ports are not usable."""


class CommandError(StackManagerError):
    """A Docker or host command returned a non-zero exit code."""

    def __init__(
        self, command: Sequence[str], returncode: int, output: str = ""
    ) -> None:
        self.command = list(command)
        self.returncode = returncode
        self.output = redact(output)
        super().__init__(f"command failed ({returncode}): {' '.join(self.command)}")


def redact(value: Any) -> str:
    """Remove product keys and common secret-bearing command fragments."""

    text = str(value or "")
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(r"\1<redacted>", text)
    product_key = os.environ.get("SPX_PRODUCT_KEY", "").strip()
    if product_key:
        text = text.replace(product_key, "<redacted>")
    return text


def _format_port_numbers(ports: Iterable[int]) -> str:
    """Render consecutive port numbers as compact ranges."""

    values = sorted({int(port) for port in ports})
    if not values:
        return "none"

    ranges: list[str] = []
    start = previous = values[0]
    for port in values[1:]:
        if port == previous + 1:
            previous = port
            continue
        ranges.append(str(start) if start == previous else f"{start}-{previous}")
        start = previous = port
    ranges.append(str(start) if start == previous else f"{start}-{previous}")
    return ", ".join(ranges)


def new_installation_id() -> str:
    """Return a short, log-friendly ID that is still globally unique."""

    return uuid.uuid4().hex


@dataclass
class ContainerInfo:
    id: str
    name: str
    image: str
    labels: dict[str, str] = field(default_factory=dict)
    state: str = ""
    status: str = ""
    health: str = ""
    ports: list[int] = field(default_factory=list)

    @property
    def project(self) -> str:
        return self.labels.get("com.docker.compose.project", "")

    @property
    def service(self) -> str:
        return self.labels.get("com.docker.compose.service", "")

    @property
    def installation_id(self) -> str:
        return self.labels.get(LABEL_INSTALLATION_ID, "")

    @property
    def running(self) -> bool:
        return self.state.lower() in {
            "running",
            "restarting",
            "paused",
        } or self.status.lower().startswith("up")


@dataclass
class ExistingStack:
    containers: list[ContainerInfo] = field(default_factory=list)
    project: str = ""
    compose_files: list[str] = field(default_factory=list)
    ports: list[int] = field(default_factory=list)
    source: str = ""

    @property
    def active(self) -> bool:
        return any(container.running for container in self.containers)

    @property
    def installation_id(self) -> str:
        values = {
            container.installation_id
            for container in self.containers
            if container.installation_id
        }
        return next(iter(values), "")

    @property
    def names(self) -> list[str]:
        return [container.name for container in self.containers]


@dataclass
class StackSnapshot:
    project: str
    installation_id: str
    containers: list[dict[str, Any]] = field(default_factory=list)
    created_at: float = 0.0

    @classmethod
    def empty(cls, project: str, installation_id: str) -> "StackSnapshot":
        return cls(
            project=project, installation_id=installation_id, created_at=time.time()
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(asdict(self), indent=2, sort_keys=True), encoding="utf-8"
        )

    @classmethod
    def load(cls, path: Path) -> "StackSnapshot":
        payload = json.loads(path.read_text(encoding="utf-8"))
        return cls(**payload)


@dataclass
class PreflightResult:
    existing: list[ExistingStack] = field(default_factory=list)
    occupied_ports: dict[int, list[str]] = field(default_factory=dict)
    required_ports: list[int] = field(default_factory=list)
    required_tcp_ports: list[int] | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def active_stacks(self) -> list[ExistingStack]:
        return [stack for stack in self.existing if stack.active]

    @property
    def conflicts(self) -> dict[int, list[str]]:
        result: dict[int, list[str]] = {}
        for port, owners in self.occupied_ports.items():
            if port not in self.required_ports or not owners:
                continue
            relevant = owners
            if (
                self.required_tcp_ports is not None
                and port not in self.required_tcp_ports
            ):
                relevant = [
                    owner
                    for owner in owners
                    if not owner.startswith("Windows excluded TCP range")
                ]
            if relevant:
                result[port] = relevant
        return result

    @property
    def unrelated_conflicts(self) -> dict[int, list[str]]:
        known_names = {
            container.name for stack in self.existing for container in stack.containers
        }
        result: dict[int, list[str]] = {}
        for port, owners in self.conflicts.items():
            unrelated = [
                owner
                for owner in owners
                if not any(owner == f"container {name}" for name in known_names)
            ]
            if unrelated:
                result[port] = unrelated
        return result


Runner = Callable[..., subprocess.CompletedProcess[str]]


class StackManager:
    """Identify and operate on the exact containers belonging to an install."""

    def __init__(
        self,
        compose_file: Path | str,
        env_file: Path | str | None = None,
        *,
        project: str = PROJECT,
        installation_id: str = "",
        runner: Runner | None = None,
        platform: str | None = None,
        transaction_token: str = "",
    ) -> None:
        self.compose_file = Path(compose_file)
        self.env_file = Path(env_file) if env_file else None
        self.project = project
        self.installation_id = installation_id
        self._runner = runner or subprocess.run
        self.platform = platform or sys.platform
        self._fallback_warnings: list[str] = []
        self.transaction_token = transaction_token
        self.last_readiness: dict[str, Any] = {}
        self._secrets: list[str] = []
        if self.env_file and self.env_file.is_file():
            for line in self.env_file.read_text(encoding="utf-8").splitlines():
                key, separator, value = line.partition("=")
                if separator and any(
                    word in key.upper()
                    for word in ("KEY", "TOKEN", "SECRET", "PASSWORD")
                ):
                    value = value.strip().strip("\"'")
                    if value:
                        self._secrets.append(value)

    # Command and inspection primitives ---------------------------------
    def _run(
        self, command: Sequence[str], *, check: bool = True, timeout: float = 30.0
    ) -> subprocess.CompletedProcess[str]:
        try:
            result = self._runner(
                list(command),
                capture_output=True,
                text=True,
                errors="replace",
                check=False,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise StackManagerError(
                f"{command[0]} {command[1] if len(command) > 1 else ''} timed out after {timeout:.1f}s"
            ) from exc
        if check and result.returncode != 0:
            output = "\n".join(part for part in (result.stdout, result.stderr) if part)
            raise CommandError(command, result.returncode, output)
        return result

    def docker(
        self, args: Sequence[str], *, check: bool = True, timeout: float = 30.0
    ) -> subprocess.CompletedProcess[str]:
        return self._run(["docker", *args], check=check, timeout=timeout)

    def compose(
        self, args: Sequence[str], *, check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        command = [
            "docker",
            "compose",
            "-p",
            self.project,
            "-f",
            str(self.compose_file),
        ]
        if self.env_file:
            command.extend(["--env-file", str(self.env_file)])
        command.extend(args)
        return self._run(command, check=check)

    def check_prerequisites(self) -> None:
        """Check CLI, daemon, Compose and the generated configuration."""

        try:
            self.docker(["version"])
        except (OSError, CommandError) as exc:
            raise PreflightError("Docker CLI is unavailable") from exc
        try:
            self.docker(["info"])
        except (OSError, CommandError) as exc:
            raise PreflightError("Docker daemon is not reachable") from exc
        try:
            self.docker(["compose", "version"])
            self.compose(["config", "--quiet"])
        except (OSError, CommandError) as exc:
            raise PreflightError(
                "Docker Compose or the generated configuration is invalid"
            ) from exc

    def list_containers(self) -> list[ContainerInfo]:
        result = self.docker(["ps", "-aq"], check=False)
        if result.returncode != 0:
            return []
        ids = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        containers: list[ContainerInfo] = []
        for container_id in ids:
            inspected = self.docker(["inspect", container_id], check=False)
            if inspected.returncode != 0:
                continue
            try:
                payload = json.loads(inspected.stdout)
                item = payload[0] if isinstance(payload, list) else payload
                containers.append(self._container_from_inspect(item))
            except (ValueError, TypeError, IndexError):
                continue
        return containers

    def _container_from_inspect(self, item: Mapping[str, Any]) -> ContainerInfo:
        config = item.get("Config") or {}
        state = item.get("State") or {}
        network = item.get("NetworkSettings") or {}
        labels = config.get("Labels") or {}
        if not isinstance(labels, Mapping):
            labels = {}
        ports = sorted(self._ports_from_inspect(item))
        return ContainerInfo(
            id=str(item.get("Id", "")),
            name=str(item.get("Name", "")).lstrip("/"),
            image=str(config.get("Image", item.get("Image", ""))),
            labels={str(key): str(value) for key, value in labels.items()},
            state=str(state.get("Status", "")),
            status=str(state.get("Status", "")),
            health=str((state.get("Health") or {}).get("Status", "")),
            ports=ports,
        )

    def _ports_from_inspect(self, item: Mapping[str, Any]) -> set[int]:
        ports: set[int] = set()
        network = item.get("NetworkSettings") or {}
        bindings = network.get("Ports") or {}
        if isinstance(bindings, Mapping):
            for values in bindings.values():
                if not values:
                    continue
                if isinstance(values, Mapping):
                    values = [values]
                for binding in values:
                    if not isinstance(binding, Mapping):
                        continue
                    raw = binding.get("HostPort")
                    if raw and str(raw).isdigit():
                        ports.add(int(raw))
        host_config = item.get("HostConfig") or {}
        bindings = host_config.get("PortBindings") or {}
        if isinstance(bindings, Mapping):
            for values in bindings.values():
                for binding in values or []:
                    if (
                        isinstance(binding, Mapping)
                        and str(binding.get("HostPort", "")).isdigit()
                    ):
                        ports.add(int(binding["HostPort"]))
        return ports

    def is_managed_container(self, container: ContainerInfo) -> bool:
        labels = container.labels
        if (
            labels.get(LABEL_STACK) == "true"
            and labels.get(LABEL_MANAGED_BY) == "installer"
        ):
            return True
        if self._uses_current_compose_file(container):
            # The exact generated Compose file is ownership evidence for its
            # third-party service containers too, such as KNX and brokers.
            return True
        if labels.get("com.docker.compose.project") == self.project:
            # A Compose project name is not an ownership proof by itself:
            # unrelated services can share the same project on a developer
            # machine. Require an expected SPX image before acting on it.
            return any(
                self._image_compatible_with_service(container.image, service)
                for service in EXPECTED_IMAGES
            )
        compose_service = labels.get("com.docker.compose.service", "")
        if compose_service in EXPECTED_IMAGES and self._image_compatible_with_service(
            container.image, compose_service
        ):
            return True
        if container.name in EXPECTED_IMAGES and self._legacy_image_compatible(
            container
        ):
            return True
        # RC65 used spx-rollback-* for temporary backups. Treat those names as
        # installer-owned only when the image is one of the known SPX services,
        # so a stale RC65 snapshot can be replaced safely without broad Docker
        # cleanup. spx-snapshot-* is the current temporary name.
        if any(container.name.startswith(prefix) for prefix in SNAPSHOT_PREFIXES):
            return any(
                self._image_compatible_with_service(container.image, service)
                for service in EXPECTED_IMAGES
            )
        return False

    def _image_compatible_with_service(self, image: str, service: str) -> bool:
        prefixes = EXPECTED_IMAGES.get(service, ())
        lowered = image.lower()
        return any(
            lowered == prefix
            or lowered.startswith(prefix + ":")
            or lowered.startswith(prefix + "@")
            for prefix in prefixes
        )

    def _legacy_image_compatible(self, container: ContainerInfo) -> bool:
        prefixes = EXPECTED_IMAGES.get(container.name)
        if not prefixes:
            return False
        return self._image_compatible_with_service(container.image, container.name)

    def _uses_current_compose_file(self, container: ContainerInfo) -> bool:
        config_files = container.labels.get(
            "com.docker.compose.project.config_files", ""
        )
        if not config_files:
            return False
        current = os.path.normcase(os.path.abspath(str(self.compose_file)))
        return any(
            os.path.normcase(os.path.abspath(candidate.strip())) == current
            for candidate in config_files.split(",")
            if candidate.strip()
        )

    def detect_existing_stacks(self) -> list[ExistingStack]:
        grouped: dict[tuple[str, str], ExistingStack] = {}
        for container in self.list_containers():
            if not self.is_managed_container(container):
                continue
            project = container.project or "legacy"
            if any(container.name.startswith(prefix) for prefix in SNAPSHOT_PREFIXES):
                source = "snapshot"
            else:
                source = (
                    "labels"
                    if container.labels.get(LABEL_STACK) == "true"
                    else "compose/legacy"
                )
            key = (project, source)
            stack = grouped.setdefault(
                key, ExistingStack(project=project, source=source)
            )
            stack.containers.append(container)
            if container.running:
                stack.ports = sorted(set(stack.ports).union(container.ports))
            compose_file = container.labels.get(
                "com.docker.compose.project.config_files", ""
            )
            if compose_file and compose_file not in stack.compose_files:
                stack.compose_files.append(compose_file)
        return list(grouped.values())

    def detect_existing_stack(self) -> ExistingStack | None:
        stacks = self.detect_existing_stacks()
        if not stacks:
            return None
        stacks.sort(key=lambda stack: (not stack.active, stack.project, stack.source))
        return stacks[0]

    def _fallback_host_ports(self) -> dict[int, list[str]]:
        owners: dict[int, list[str]] = {}
        self._fallback_warnings = []
        if self.platform.startswith("win"):
            script = (
                "$ErrorActionPreference='Stop'; "
                "$serviceCache=@{}; "
                "Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | "
                "ForEach-Object { $connection=$_; "
                "$process=Get-Process -Id $connection.OwningProcess -ErrorAction SilentlyContinue; "
                "$processName='unknown'; if($process){$processName=$process.ProcessName}; "
                "$serviceNames=''; if($processName -eq 'svchost'){ "
                "$processId=[int]$connection.OwningProcess; "
                "if(-not $serviceCache.ContainsKey($processId)){ "
                "$serviceCache[$processId]=@(Get-CimInstance Win32_Service "
                '-Filter "ProcessId = $processId" -ErrorAction SilentlyContinue '
                "| Select-Object -ExpandProperty Name) -join ',' }; "
                "$serviceNames=[string]$serviceCache[$processId] }; "
                "[PSCustomObject]@{LocalPort=$connection.LocalPort; "
                "ProcessId=$connection.OwningProcess; "
                "ProcessName=$processName; ServiceNames=$serviceNames} } | "
                "ConvertTo-Json -Compress"
            )
            command = ["powershell", "-NoProfile", "-Command", script]
        elif shutil.which("lsof"):
            command = ["lsof", "-nP", "-iTCP", "-sTCP:LISTEN", "-Fpcn"]
        elif shutil.which("ss"):
            command = ["ss", "-ltnp"]
        else:
            return owners
        try:
            result = self._run(command, check=False)
        except OSError as exc:
            if self.platform.startswith("win"):
                self._fallback_warnings.append(
                    f"Could not inspect Windows TCP listeners: {exc}"
                )
                self._add_windows_excluded_tcp_ports(owners)
            return owners
        if self.platform.startswith("win"):
            try:
                payload = json.loads(result.stdout or "[]")
                rows = payload if isinstance(payload, list) else [payload]
                for row in rows:
                    if (
                        isinstance(row, Mapping)
                        and str(row.get("LocalPort", "")).isdigit()
                    ):
                        port = int(row["LocalPort"])
                        if 1 <= port <= 65535:
                            process_name = str(row.get("ProcessName") or "").strip()
                            process_id = str(row.get("ProcessId") or "").strip()
                            service_names = str(row.get("ServiceNames") or "").strip()
                            owner = self._host_process_owner(
                                process_name, process_id, service_names
                            )
                            port_owners = owners.setdefault(port, [])
                            if owner not in port_owners:
                                port_owners.append(owner)
            except (TypeError, ValueError):
                self._fallback_warnings.append(
                    "Could not parse Windows TCP listener information; reserved ranges will still be checked."
                )
            self._add_windows_excluded_tcp_ports(owners)
            return owners
        if command[0] == "lsof":
            process_id = ""
            process_name = ""
            for line in (result.stdout or "").splitlines():
                if line.startswith("p"):
                    process_id = line[1:]
                elif line.startswith("c"):
                    process_name = line[1:]
                elif line.startswith("n"):
                    match = re.search(r":(\d{1,5})(?:\s|$)", line[1:])
                    if match:
                        port = int(match.group(1))
                        if 1 <= port <= 65535:
                            owner = self._host_process_owner(process_name, process_id)
                            port_owners = owners.setdefault(port, [])
                            if owner not in port_owners:
                                port_owners.append(owner)
            return owners

        for line in (result.stdout or "").splitlines():
            fields = line.split(None, 5)
            if len(fields) < 5:
                continue
            match = re.search(r":(\d{1,5})$", fields[3])
            if not match:
                continue
            port = int(match.group(1))
            if not 1 <= port <= 65535:
                continue
            processes = re.findall(r'\("([^" ]+)",pid=(\d+)', line)
            labels = [self._host_process_owner(name, pid) for name, pid in processes]
            port_owners = owners.setdefault(port, [])
            for owner in labels or ["host process"]:
                if owner not in port_owners:
                    port_owners.append(owner)
        return owners

    @staticmethod
    def _parse_windows_excluded_port_range_output(
        output: str, family: str
    ) -> dict[int, list[str]]:
        """Parse netsh's numeric excluded-port table without relying on its locale."""

        owners: dict[int, list[str]] = {}
        for line in output.splitlines():
            match = re.match(r"^\s*(\d+)\s+(\d+)(?:\s+\*)?(?:\s|$)", line)
            if not match:
                continue
            start, end = (int(value) for value in match.groups())
            if not 1 <= start <= end <= 65535:
                continue
            owner = f"Windows excluded TCP range ({family}) {start}-{end}"
            for port in range(start, end + 1):
                owners.setdefault(port, []).append(owner)
        return owners

    def _add_windows_excluded_tcp_ports(self, owners: dict[int, list[str]]) -> None:
        for family in ("ipv4", "ipv6"):
            command = [
                "netsh",
                "interface",
                family,
                "show",
                "excludedportrange",
                "protocol=tcp",
            ]
            try:
                result = self._run(command, check=False)
            except OSError as exc:
                self._fallback_warnings.append(
                    f"Could not inspect Windows {family.upper()} excluded TCP ranges: {exc}"
                )
                continue
            if result.returncode != 0:
                details = (result.stderr or result.stdout or "").strip()
                suffix = f" ({details})" if details else ""
                self._fallback_warnings.append(
                    f"Could not inspect Windows {family.upper()} excluded TCP ranges{suffix}."
                )
                continue
            for port, labels in self._parse_windows_excluded_port_range_output(
                result.stdout or "", family.upper()
            ).items():
                values = owners.setdefault(port, [])
                values.extend(label for label in labels if label not in values)

    @staticmethod
    def _host_process_owner(
        process_name: str = "", process_id: str = "", service_names: str = ""
    ) -> str:
        details = process_name.strip()
        identifiers = []
        if process_id.isdigit():
            identifiers.append(f"PID {process_id}")
        names = [name.strip() for name in service_names.split(",") if name.strip()]
        if names:
            identifiers.append(f"services {', '.join(names)}")
        if identifiers:
            suffix = "; ".join(identifiers)
            details = f"{details} ({suffix})" if details else suffix
        return f"process {details}" if details else "host process"

    def occupied_ports(self) -> dict[int, list[str]]:
        owners: dict[int, list[str]] = {}
        for container in self.list_containers():
            # Docker inspect retains HostConfig.PortBindings for exited
            # containers. Those bindings do not occupy host ports and must
            # not block startup or the user's retry loop.
            if not getattr(container, "running", True):
                continue
            for port in container.ports:
                owners.setdefault(port, []).append(
                    f"container {container.name or container.id[:12]}"
                )
        for port, values in self._fallback_host_ports().items():
            # Docker Desktop exposes the same published port through its host
            # proxy. Docker inspect is authoritative for those ports; adding
            # the proxy as a second owner would make a related SPX stack look
            # like an unrelated conflict and block a safe replacement.
            if port in owners:
                continue
            owners.setdefault(port, []).extend(
                value for value in values if value not in owners.get(port, [])
            )
        return owners

    def preflight(
        self,
        required_ports: Iterable[int] = (),
        *,
        required_tcp_ports: Iterable[int] | None = None,
    ) -> PreflightResult:
        self.check_prerequisites()
        occupied = self.occupied_ports()
        return PreflightResult(
            existing=self.detect_existing_stacks(),
            occupied_ports=occupied,
            required_ports=sorted(
                {int(port) for port in required_ports if int(port) > 0}
            ),
            required_tcp_ports=(
                None
                if required_tcp_ports is None
                else sorted({int(port) for port in required_tcp_ports if int(port) > 0})
            ),
            warnings=list(self._fallback_warnings),
        )

    def describe(
        self, result: PreflightResult, output: Callable[[str], None] = print
    ) -> None:
        for warning in result.warnings:
            output(f"[spx-preflight] Warning: {warning}")
        for stack in result.existing:
            images = ", ".join(
                f"{container.name}: {container.image} "
                f"(state={getattr(container, 'state', '') or 'unknown'}, "
                f"health={container.health or 'unknown'})"
                for container in stack.containers
            )
            config = ", ".join(stack.compose_files) or "not reported by Docker"
            ports = _format_port_numbers(stack.ports)
            output(
                f"[spx-preflight] Existing stack: project={stack.project}, "
                f"config={config}, ports={ports}\n  {images}"
            )
        known_container_owners = {
            f"container {container.name}"
            for stack in result.existing
            for container in stack.containers
        }
        existing_conflicts: dict[str, list[int]] = {}
        unrelated_conflicts: dict[str, list[int]] = {}
        for port, owners in result.conflicts.items():
            existing_stack_owners = [
                owner for owner in owners if owner in known_container_owners
            ]
            unrelated_owners = [
                owner for owner in owners if owner not in known_container_owners
            ]
            for owner in existing_stack_owners:
                existing_conflicts.setdefault(owner, []).append(port)
            for owner in unrelated_owners:
                unrelated_conflicts.setdefault(owner, []).append(port)

        for owner, ports in sorted(existing_conflicts.items()):
            output(
                f"[spx-preflight] Detected SPX stack uses required host port(s) "
                f"{_format_port_numbers(ports)} ({owner}). Approve replacement to release them."
            )
        for owner, ports in sorted(unrelated_conflicts.items()):
            output(
                f"[spx-preflight] Required host port(s) {_format_port_numbers(ports)} "
                f"are already in use by {owner}."
            )

    def _detach_snapshot_container(self, container_id: str) -> None:
        """Keep a renamed backup out of the next Compose project discovery."""

        labels = (
            "com.docker.compose.project",
            "com.docker.compose.service",
            "com.docker.compose.container-number",
            "com.docker.compose.config-hash",
            "com.docker.compose.project.config_files",
            "com.docker.compose.project.working_dir",
            "com.docker.compose.project.environment_file",
            LABEL_STACK,
            LABEL_MANAGED_BY,
            LABEL_PROJECT,
            LABEL_INSTALLATION_ID,
        )
        for label in labels:
            self._run(
                ["docker", "update", "--label-rm", label, container_id], check=False
            )

    def snapshot_existing(
        self, stack: ExistingStack, snapshot_path: Path
    ) -> StackSnapshot:
        snapshot = StackSnapshot.empty(self.project, self.installation_id)
        for container in stack.containers:
            original_name = container.name
            if container.running:
                self._run(["docker", "stop", container.id])
            snapshot_name = f"spx-snapshot-{container.id[:12]}"
            if original_name != snapshot_name:
                self._run(["docker", "rename", container.id, snapshot_name])
            self._detach_snapshot_container(container.id)
            snapshot.containers.append(
                {
                    "id": container.id,
                    "name": original_name,
                    "snapshot_name": snapshot_name,
                }
            )
        snapshot.save(snapshot_path)
        return snapshot

    def prepare(
        self,
        snapshot_path: Path,
        *,
        required_ports: Iterable[int] = (),
        required_tcp_ports: Iterable[int] | None = None,
        assume_yes: bool = False,
        input_fn: Callable[[str], str] | None = None,
        output: Callable[[str], None] = print,
    ) -> PreflightResult:
        if self.env_file is not None:
            try:
                validate_product_key_format(runtime_product_key(self.env_file))
            except ValueError as exc:
                raise PreflightError(str(exc)) from exc
        normalized_ports: set[int] = set()
        for port in required_ports:
            value = int(port)
            if value > 0:
                normalized_ports.add(value)
        required_ports = sorted(normalized_ports)
        normalized_tcp_ports = (
            None
            if required_tcp_ports is None
            else sorted(
                {int(port) for port in required_tcp_ports if 1 <= int(port) <= 65535}
            )
        )
        if input_fn is not None:
            can_prompt = True
            prompt = input_fn
        else:
            try:
                can_prompt = sys.stdin is not None and sys.stdin.isatty()
            except (AttributeError, OSError):
                can_prompt = False
            prompt = input
        result = self.preflight(required_ports, required_tcp_ports=normalized_tcp_ports)
        approved = os.environ.get("SPX_SETUP_APPROVED_STACK")
        if approved is not None:
            # Dependencies may have been installed since the agent reviewed its
            # plan. Recheck immediately before snapshot/stop, not only at queue time.
            current = {
                "containers": sorted(
                    [c.id, c.name, c.image, c.state]
                    for stack in result.existing
                    if stack.source != "snapshot"
                    for c in stack.containers
                ),
                "ports": required_ports,
            }
            try:
                matches = json.loads(approved) == current
            except (ValueError, TypeError):
                matches = False
            if not matches:
                raise PreflightError(
                    "Stack or ports changed after the approved plan. Request a new Setup plan and approval; no containers were stopped."
                )
            can_prompt = False
        self.describe(result, output)
        while result.unrelated_conflicts:
            if not can_prompt:
                raise PreflightError(
                    "Some required ports are in use. Stop or reconfigure the listed applications or containers, "
                    "then run SPX Setup again."
                )
            output(
                "[spx-preflight] Stop or reconfigure the listed applications or containers yourself; "
                "SPX Setup will not stop unrelated software."
            )
            try:
                answer = prompt(
                    "[spx-preflight] Press Enter to check the ports again, or type Q to quit: "
                )
            except EOFError as exc:
                raise PreflightError(
                    "No terminal input is available. Stop or reconfigure the listed applications or containers, "
                    "then run SPX Setup again."
                ) from exc
            choice = answer.strip().lower()
            if choice == "q":
                raise UserDeclined(
                    "Setup cancelled. Free the listed ports and run SPX Setup again."
                )
            if choice:
                output("[spx-preflight] Press Enter to check again, or type Q to quit.")
                continue
            output("[spx-preflight] Checking the required ports again...")
            result = self.preflight(
                required_ports, required_tcp_ports=normalized_tcp_ports
            )
            self.describe(result, output)

        replaceable = [stack for stack in result.existing if stack.containers]
        if replaceable:
            if not assume_yes:
                if not can_prompt:
                    raise UserDeclined(
                        "A detected SPX stack was left untouched because approval requires an interactive terminal. "
                        "Run SPX Setup interactively to review and approve replacement."
                    )
                answer = (
                    prompt("[spx-preflight] Replace the detected SPX stack? [y/N]: ")
                    .strip()
                    .lower()
                )
                if answer not in {"y", "yes"}:
                    raise UserDeclined(
                        "Existing SPX stack was left untouched; compose up was not run"
                    )
            combined = ExistingStack(
                containers=[
                    container for stack in replaceable for container in stack.containers
                ],
                project=replaceable[0].project,
                compose_files=sorted(
                    {path for stack in replaceable for path in stack.compose_files}
                ),
                ports=sorted({port for stack in replaceable for port in stack.ports}),
                source=replaceable[0].source,
            )
            self.snapshot_existing(combined, snapshot_path)
        else:
            StackSnapshot.empty(self.project, self.installation_id).save(snapshot_path)
        return result

    def transaction_containers(self) -> list[ContainerInfo]:
        if not self.installation_id:
            return []
        if self.transaction_token:
            # Compose service labels survive commit's container renames.
            return self._readiness_containers(time.monotonic() + 15.0)
        return [
            container
            for container in self.list_containers()
            if container.installation_id == self.installation_id
            and container.name.startswith("spx-transaction-")
        ]

    def _remaining(self, deadline: float, maximum: float = 5.0) -> float:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise StackManagerError("Readiness deadline reached")
        return min(maximum, remaining)

    def _inspect_ids(self, ids: Sequence[str], deadline: float) -> list[ContainerInfo]:
        if not ids:
            return []
        result = self.docker(["inspect", *ids], timeout=self._remaining(deadline))
        try:
            payload = json.loads(result.stdout)
            if not isinstance(payload, list) or len(payload) != len(ids):
                raise ValueError("Unexpected Docker inspect result")
            return [self._container_from_inspect(item) for item in payload]
        except (ValueError, TypeError, AttributeError) as exc:
            raise StackManagerError("Could not decode Docker inspect result") from exc

    def _readiness_containers(self, deadline: float) -> list[ContainerInfo]:
        if not self.installation_id:
            raise StackManagerError("Installation ID is missing")
        prefix = "spx-transaction-" + (
            self.transaction_token + "-" if self.transaction_token else ""
        )
        result = self.docker(
            [
                "ps",
                "-aq",
                "--filter",
                f"label={LABEL_INSTALLATION_ID}={self.installation_id}",
                "--filter",
                f"label=com.docker.compose.project={self.project}",
            ],
            timeout=self._remaining(deadline),
        )
        return [
            item
            for item in self._inspect_ids(result.stdout.split(), deadline)
            if item.installation_id == self.installation_id
            and (
                item.name.startswith(prefix)
                or (
                    self.transaction_token
                    and item.service.startswith(
                        f"transaction-{self.transaction_token}-"
                    )
                )
            )
        ]

    def _is_server(self, item: ContainerInfo) -> bool:
        return (
            item.name == "spx-server"
            or item.service == "spx-server"
            or item.service.endswith("-spx-server")
            or self._image_compatible_with_service(item.image, "spx-server")
        )

    def _safe_text(self, value: Any) -> str:
        text = redact(value)
        for secret in self._secrets:
            text = text.replace(secret, "<redacted>")
        text = re.sub(
            r"(?i)(authorization\s*[:=]\s*(?:bearer\s+)?)[^\s\"',;]+",
            r"\1<redacted>",
            text,
        )
        return re.sub(r"(https?://)[^/@\s]+@", r"\1<redacted>@", text)

    def _error_detail(self, exc: Exception) -> str:
        detail = str(exc)
        if isinstance(exc, CommandError) and exc.output:
            detail += ": " + exc.output.strip()[:600]
        return self._safe_text(detail)

    def _probe_api(self, api_url: str, timeout: float = 3.0) -> dict[str, Any]:
        url = api_url.rstrip("/") + "/health"
        result: dict[str, Any] = {"url": self._safe_text(url), "ready": False}
        try:
            request = urllib.request.Request(url, method="GET")
            parsed = urlsplit(url)
            loopback = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
            if parsed.scheme == "http" and loopback:
                # urllib builds an HTTPS handler even for plain HTTP. On Python
                # 3.12 that opens SSLKEYLOGFILE, which may be inaccessible in a
                # GUI launcher's environment. A local HTTP probe needs no TLS.
                connection = HTTPConnection(
                    parsed.hostname, parsed.port, timeout=timeout
                )
                try:
                    connection.request("GET", request.selector)
                    with connection.getresponse() as response:
                        status = response.status
                finally:
                    connection.close()
            else:
                # Preserve normal HTTPS handling, without proxying local probes.
                if loopback:
                    open_url = urllib.request.build_opener(
                        urllib.request.ProxyHandler({})
                    ).open
                else:
                    open_url = urllib.request.urlopen
                with open_url(request, timeout=timeout) as response:
                    status = response.status
            result.update(status=status, ready=200 <= status < 300)
            if not result["ready"]:
                result["error"] = f"HTTP {status}"
        except urllib.error.HTTPError as exc:
            result.update(status=exc.code, error=f"HTTP {exc.code}")
        except (OSError, urllib.error.URLError, ValueError, HTTPException) as exc:
            result.update(
                error_type=type(exc).__name__, error=self._safe_text(str(exc))
            )
        return result

    def capture_diagnostics(self, path: Path, reason: str = "") -> None:
        """Preserve curated state and bounded logs before removing failed containers."""
        report: dict[str, Any] = {
            "installation_id": self.installation_id,
            "reason": reason,
            "readiness": self.last_readiness,
            "containers": [],
        }
        if path.exists():
            try:
                previous = json.loads(path.read_text(encoding="utf-8"))
                if not report["readiness"]:
                    report["readiness"] = previous.get("readiness", {})
            except (OSError, ValueError):
                pass
        try:
            for item in self._readiness_containers(time.monotonic() + 15.0):
                entry = {
                    "id": item.id,
                    "name": item.name,
                    "image": item.image,
                    "state": item.state,
                    "health": item.health,
                }
                if self._is_server(item) or item.service.endswith("-spx-ui"):
                    try:
                        logs = self.docker(
                            ["logs", "--tail", "60", item.id], check=False, timeout=5.0
                        )
                        entry["logs"] = (logs.stdout + logs.stderr)[-12000:]
                    except (StackManagerError, OSError) as exc:
                        entry["log_error"] = self._error_detail(exc)
                report["containers"].append(entry)
        except (StackManagerError, OSError) as exc:
            report["inspection_error"] = self._error_detail(exc)

        def clean(value: Any) -> Any:
            if isinstance(value, str):
                return self._safe_text(value)
            if isinstance(value, dict):
                return {key: clean(item) for key, item in value.items()}
            if isinstance(value, list):
                return [clean(item) for item in value]
            return value

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(clean(report), indent=2), encoding="utf-8")
        print(f"[spx-preflight] Diagnostics saved to {path}")

    def stop_stack(self) -> None:
        current = [
            container
            for container in self.list_containers()
            if container.installation_id == self.installation_id
            and (
                container.name in EXPECTED_IMAGES
                or container.name.startswith("spx-transaction-")
            )
        ]
        for container in current:
            if container.running:
                self._run(["docker", "stop", container.id], check=False)

    def stop_transaction(self) -> None:
        """Backward-compatible alias for stopping the current stack."""

        self.stop_stack()

    def commit(
        self, snapshot_path: Path, final_names: Mapping[str, str] | None = None
    ) -> None:
        """Commit a successful replacement and remove only exact old IDs."""

        final_names = dict(final_names or {})
        for container in self.transaction_containers():
            target_name = final_names.get(container.service)
            if not target_name:
                target_name = next(
                    (
                        final_name
                        for service_name, final_name in final_names.items()
                        if container.service.endswith(f"-{service_name}")
                    ),
                    None,
                )
            if not target_name or container.name == target_name:
                continue
            result = self._run(
                ["docker", "rename", container.id, target_name], check=False
            )
            if result.returncode != 0:
                raise StackManagerError(
                    f"Could not assign stable name {target_name} to transaction container {container.id[:12]}"
                )

        if not snapshot_path.exists():
            return
        snapshot = StackSnapshot.load(snapshot_path)
        for entry in snapshot.containers:
            container_id = str(entry.get("id", ""))
            if not container_id:
                continue
            # The snapshot containers are stopped before Compose starts the new
            # stack. Keep the operation exact and never pass -v: volumes and
            # images are intentionally outside the installer's cleanup scope.
            self._run(["docker", "stop", container_id], check=False)
            # -f is scoped to this exact, already-snapshotted container. It
            # handles Docker Desktop races where a stopped snapshot transitions
            # state between stop and rm; omitting -v preserves its volumes.
            result = self._run(["docker", "rm", "-f", container_id], check=False)
            if result.returncode != 0:
                raise StackManagerError(
                    f"Could not remove committed snapshot container {container_id[:12]}"
                )
        snapshot_path.unlink(missing_ok=True)

    def rollback(
        self,
        snapshot_path: Path,
        api_url: str = "http://127.0.0.1:8000",
        timeout: float = 120.0,
    ) -> None:
        current = self.transaction_containers()
        for container in current:
            if container.running:
                self._run(["docker", "stop", container.id], check=False)
        # Current transaction containers still own the compatibility names.
        for container in current:
            self._run(
                ["docker", "rename", container.id, f"spx-failed-{container.id[:12]}"],
                check=False,
            )
            self._detach_snapshot_container(container.id)
            # Remove only the failed transaction container. Docker volumes are
            # preserved because this command deliberately omits -v.
            result = self._run(["docker", "rm", "-f", container.id], check=False)
            if result.returncode:
                raise StackManagerError(
                    f"Could not remove failed transaction container {container.name}; snapshot retained"
                )
        if not snapshot_path.exists():
            raise StackManagerError(f"Rollback snapshot is missing: {snapshot_path}")
        snapshot = StackSnapshot.load(snapshot_path)
        setup_journal = os.environ.get("SPX_SETUP_JOURNAL")
        if setup_journal:
            if __package__:
                from .deployment_journal import restore_files
            else:
                from deployment_journal import restore_files
            previous_api_url = restore_files(Path(setup_journal), mounts_only=True)
            if previous_api_url and snapshot.containers:
                api_url = previous_api_url
        failures: list[str] = []
        ids: list[str] = []
        for entry in snapshot.containers:
            container_id = str(entry.get("id", ""))
            original_name = str(entry.get("name", ""))
            if not container_id or not original_name:
                failures.append("Invalid snapshot container entry")
                continue
            ids.append(container_id)
            result = self._run(
                ["docker", "rename", container_id, original_name], check=False
            )
            if result.returncode == 0:
                if (
                    self._run(["docker", "start", container_id], check=False).returncode
                    != 0
                ):
                    failures.append(f"Could not start {original_name}")
            else:
                failures.append(f"Could not restore name {original_name}")
        if failures:
            raise StackManagerError(
                "Rollback incomplete: "
                + "; ".join(failures)
                + f". Snapshot retained: {snapshot_path}"
            )
        if ids:
            deadline = time.monotonic() + timeout
            reason = "Restored containers are not ready"
            while time.monotonic() < deadline:
                try:
                    restored = self._inspect_ids(ids, deadline)
                    server = next(
                        (item for item in restored if self._is_server(item)), None
                    )
                    reason = "; ".join(
                        f"{item.name} state={item.state} health={item.health or 'none'}"
                        for item in restored
                    )
                    if len(restored) == len(ids) and all(
                        item.state == "running" and item.health in {"", "healthy"}
                        for item in restored
                    ):
                        api = (
                            self._probe_api(api_url, self._remaining(deadline, 3.0))
                            if server
                            else {"ready": True}
                        )
                        if api["ready"] and time.monotonic() < deadline:
                            break
                        reason += "; " + api.get(
                            "error", "Host API not ready before deadline"
                        )
                except (StackManagerError, OSError) as exc:
                    reason = self._error_detail(exc)
                time.sleep(max(0.0, min(2.0, deadline - time.monotonic())))
            else:
                raise StackManagerError(
                    f"Rollback not ready: {reason}. Snapshot retained: {snapshot_path}"
                )
            versions = ", ".join(f"{item.name}: {item.image}" for item in restored)
            readiness = "host API ready" if server else "containers ready"
            print(
                f"[spx-preflight] Rollback verified: previous stack restored ({versions}); {readiness}."
            )
        else:
            print(
                "[spx-preflight] Failed installation removed; no previous stack to restore."
            )
        snapshot_path.unlink(missing_ok=True)
        print(
            "[spx-preflight] Run SPX Setup from the SPX application / Start menu to retry setup."
        )

    def wait_health(
        self, api_url: str = "http://127.0.0.1:8000", timeout: float = 120.0
    ) -> None:
        deadline = time.monotonic() + timeout
        started = time.monotonic()
        last_message = ""
        last_log = started
        required_services = []
        bundle_path = self.compose_file.parent / "bundle.json"
        if bundle_path.exists():
            try:
                required_services = json.loads(
                    bundle_path.read_text(encoding="utf-8")
                ).get("required_compose_services", [])
                if not isinstance(required_services, list) or any(
                    not isinstance(s, str) or not s for s in required_services
                ):
                    raise ValueError("Invalid required service list")
            except (OSError, ValueError, AttributeError) as exc:
                raise StackManagerError(
                    "Could not validate required services in the installation bundle"
                ) from exc
        while time.monotonic() < deadline:
            state: dict[str, Any] = {"url": self._safe_text(api_url), "ready": False}
            try:
                containers = self._readiness_containers(deadline)
                servers = [item for item in containers if self._is_server(item)]
                if len(servers) != 1:
                    state["reason"] = (
                        f"Expected one transaction SPX server; found {len(servers)}"
                    )
                else:
                    server = servers[0]
                    state["server"] = {
                        "id": server.id,
                        "name": server.name,
                        "state": server.state,
                        "health": server.health,
                    }
                    if server.state != "running" or server.health not in {
                        "",
                        "healthy",
                    }:
                        state["reason"] = (
                            f"{server.name}: state={server.state}, health={server.health or 'none'}"
                        )
                    else:
                        api = self._probe_api(api_url, self._remaining(deadline, 3.0))
                        state["api"] = api
                        state["ready"] = api["ready"] and time.monotonic() < deadline
                        state["reason"] = (
                            "Host API ready"
                            if state["ready"]
                            else api.get("error", "Host API not ready")
                        )
                if required_services:
                    checked = {}
                    for service in required_services:
                        service_label = (
                            f"transaction-{self.transaction_token}-{service}"
                            if self.transaction_token
                            else service
                        )
                        matches = [
                            item for item in containers if item.service == service_label
                        ]
                        item = matches[0] if len(matches) == 1 else None
                        checked[service] = {
                            "state": item.state if item else "missing",
                            "health": item.health if item else "",
                            "ready": bool(
                                item
                                and item.state == "running"
                                and item.health in {None, "", "healthy"}
                            ),
                        }
                    state["services"] = checked
                    failed = [
                        sid for sid, result in checked.items() if not result["ready"]
                    ]
                    if failed:
                        state["ready"] = False
                        state["reason"] = "Required services not ready: " + ", ".join(
                            f"{sid} ({checked[sid]['state']}, {checked[sid]['health'] or 'no healthcheck'})"
                            for sid in failed
                        )
            except (StackManagerError, OSError) as exc:
                state["reason"] = self._error_detail(exc)
            state["elapsed_s"] = round(time.monotonic() - started, 1)
            self.last_readiness = state
            message = self._safe_text(state["reason"])
            if message != last_message or time.monotonic() - last_log >= 15.0:
                print(
                    f"[spx-preflight] Readiness ({state['elapsed_s']:.1f}s): {message}; API={self._safe_text(api_url)}",
                    flush=True,
                )
                last_message, last_log = message, time.monotonic()
            if state["ready"]:
                return
            time.sleep(max(0.0, min(2.0, deadline - time.monotonic())))
        raise StackManagerError(
            f"SPX healthcheck/API did not become ready within {timeout:.0f} seconds: {last_message or 'deadline reached'}"
        )

    def _api_healthy(self, api_url: str) -> bool:
        return bool(self._probe_api(api_url)["ready"])


def _parse_ports(raw: str) -> list[int]:
    ports: list[int] = []
    for value in (part.strip() for part in raw.split(",")):
        if value.isdigit() and 1 <= int(value) <= 65535:
            ports.append(int(value))
    return sorted(set(ports))


def _parse_optional_ports(raw: str | None) -> list[int] | None:
    return None if raw is None else _parse_ports(raw)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Safely manage an installer-owned SPX Docker stack"
    )
    parser.add_argument(
        "command",
        choices=[
            "preflight",
            "prepare",
            "rollback",
            "commit",
            "stop",
            "wait-health",
            "diagnose",
        ],
    )
    parser.add_argument("--compose-file", required=True)
    parser.add_argument("--env-file", default=None)
    parser.add_argument("--project", default=PROJECT)
    parser.add_argument("--installation-id", default="")
    parser.add_argument("--transaction-token", default="")
    parser.add_argument("--diagnostics-path", type=Path)
    parser.add_argument("--failure-stage", default="")
    parser.add_argument("--snapshot", default=".spx-stack-snapshot.json")
    parser.add_argument("--ports", default="")
    parser.add_argument("--tcp-ports", default=None)
    parser.add_argument(
        "--yes", action="store_true", help="Accept replacement of an existing stack"
    )
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument(
        "--final-name", action="append", default=[], metavar="SERVICE=CONTAINER"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manager = StackManager(
        args.compose_file,
        args.env_file,
        project=args.project,
        installation_id=args.installation_id,
        transaction_token=args.transaction_token,
    )
    snapshot_path = Path(args.snapshot)
    if args.command == "preflight":
        result = manager.preflight(
            _parse_ports(args.ports),
            required_tcp_ports=_parse_optional_ports(args.tcp_ports),
        )
        manager.describe(result)
        if result.unrelated_conflicts:
            raise PreflightError("Required ports are already occupied")
        return 0
    if args.command == "prepare":
        manager.prepare(
            snapshot_path,
            required_ports=_parse_ports(args.ports),
            required_tcp_ports=_parse_optional_ports(args.tcp_ports),
            assume_yes=args.yes,
        )
        return 0
    if args.command == "rollback":
        manager.rollback(snapshot_path, args.api_url, args.timeout)
        return 0
    if args.command == "commit":
        final_names = {}
        for raw in args.final_name:
            if "=" not in raw:
                raise StackManagerError(f"Invalid final container name mapping: {raw}")
            service, container = raw.split("=", 1)
            if service and container:
                final_names[service] = container
        manager.commit(snapshot_path, final_names)
        return 0
    if args.command == "stop":
        manager.stop_stack()
        return 0
    if args.command == "wait-health":
        try:
            manager.wait_health(args.api_url, args.timeout)
        except (StackManagerError, OSError):
            if args.diagnostics_path:
                try:
                    manager.capture_diagnostics(
                        args.diagnostics_path, "healthcheck failed"
                    )
                except OSError as exc:
                    print(
                        f"[spx-preflight] Could not save diagnostics: {manager._safe_text(str(exc))}",
                        file=sys.stderr,
                    )
            raise
        return 0
    if args.command == "diagnose":
        if not args.diagnostics_path:
            raise StackManagerError("Diagnostics path is required")
        manager.capture_diagnostics(args.diagnostics_path, args.failure_stage)
        return 0
    return 2


if __name__ == "__main__":  # pragma: no cover
    try:
        raise SystemExit(main())
    except UserDeclined as exc:
        print(f"[spx-preflight] {redact(exc)}", file=sys.stderr)
        raise SystemExit(3)
    except (StackManagerError, OSError) as exc:
        print(f"[spx-preflight] {redact(exc)}", file=sys.stderr)
        raise SystemExit(1)
