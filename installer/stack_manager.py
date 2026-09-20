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
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence


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

    def __init__(self, command: Sequence[str], returncode: int, output: str = "") -> None:
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
        return self.state.lower() == "running" or self.status.lower().startswith("up")


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
        values = {container.installation_id for container in self.containers if container.installation_id}
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
        return cls(project=project, installation_id=installation_id, created_at=time.time())

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2, sort_keys=True), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "StackSnapshot":
        payload = json.loads(path.read_text(encoding="utf-8"))
        return cls(**payload)


@dataclass
class PreflightResult:
    existing: list[ExistingStack] = field(default_factory=list)
    occupied_ports: dict[int, list[str]] = field(default_factory=dict)
    required_ports: list[int] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def active_stacks(self) -> list[ExistingStack]:
        return [stack for stack in self.existing if stack.active]

    @property
    def conflicts(self) -> dict[int, list[str]]:
        return {
            port: owners
            for port, owners in self.occupied_ports.items()
            if port in self.required_ports and owners
        }

    @property
    def unrelated_conflicts(self) -> dict[int, list[str]]:
        known_names = {
            container.name
            for stack in self.existing
            for container in stack.containers
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
    ) -> None:
        self.compose_file = Path(compose_file)
        self.env_file = Path(env_file) if env_file else None
        self.project = project
        self.installation_id = installation_id
        self._runner = runner or subprocess.run
        self.platform = platform or sys.platform

    # Command and inspection primitives ---------------------------------
    def _run(self, command: Sequence[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
        result = self._runner(
            list(command),
            capture_output=True,
            text=True,
            check=False,
        )
        if check and result.returncode != 0:
            output = "\n".join(part for part in (result.stdout, result.stderr) if part)
            raise CommandError(command, result.returncode, output)
        return result

    def docker(self, args: Sequence[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
        return self._run(["docker", *args], check=check)

    def compose(self, args: Sequence[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
        command = ["docker", "compose", "-p", self.project, "-f", str(self.compose_file)]
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
            raise PreflightError("Docker Compose or the generated configuration is invalid") from exc

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
                    if isinstance(binding, Mapping) and str(binding.get("HostPort", "")).isdigit():
                        ports.add(int(binding["HostPort"]))
        return ports

    def is_managed_container(self, container: ContainerInfo) -> bool:
        labels = container.labels
        if labels.get(LABEL_STACK) == "true" and labels.get(LABEL_MANAGED_BY) == "installer":
            return True
        if labels.get("com.docker.compose.project") == self.project:
            return True
        compose_service = labels.get("com.docker.compose.service", "")
        if compose_service in EXPECTED_IMAGES and self._image_compatible_with_service(
            container.image, compose_service
        ):
            return True
        if container.name in EXPECTED_IMAGES and self._legacy_image_compatible(container):
            return True
        return False

    def _image_compatible_with_service(self, image: str, service: str) -> bool:
        prefixes = EXPECTED_IMAGES.get(service, ())
        lowered = image.lower()
        return any(
            lowered == prefix or lowered.startswith(prefix + ":") or lowered.startswith(prefix + "@")
            for prefix in prefixes
        )

    def _legacy_image_compatible(self, container: ContainerInfo) -> bool:
        prefixes = EXPECTED_IMAGES.get(container.name)
        if not prefixes:
            return False
        return self._image_compatible_with_service(container.image, container.name)

    def detect_existing_stacks(self) -> list[ExistingStack]:
        grouped: dict[tuple[str, str], ExistingStack] = {}
        for container in self.list_containers():
            if not self.is_managed_container(container):
                continue
            project = container.project or "legacy"
            source = "labels" if container.labels.get(LABEL_STACK) == "true" else "compose/legacy"
            key = (project, source)
            stack = grouped.setdefault(key, ExistingStack(project=project, source=source))
            stack.containers.append(container)
            stack.ports = sorted(set(stack.ports).union(container.ports))
            compose_file = container.labels.get("com.docker.compose.project.config_files", "")
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
        if self.platform.startswith("win"):
            command = ["powershell", "-NoProfile", "-Command", "Get-NetTCPConnection -State Listen | ConvertTo-Json -Compress"]
        elif shutil.which("lsof"):
            command = ["lsof", "-nP", "-iTCP", "-sTCP:LISTEN"]
        elif shutil.which("ss"):
            command = ["ss", "-ltnp"]
        else:
            return owners
        try:
            result = self._run(command, check=False)
        except OSError:
            return owners
        if self.platform.startswith("win"):
            try:
                payload = json.loads(result.stdout or "[]")
                rows = payload if isinstance(payload, list) else [payload]
                for row in rows:
                    if isinstance(row, Mapping) and str(row.get("LocalPort", "")).isdigit():
                        port = int(row["LocalPort"])
                        if 1 <= port <= 65535:
                            owners.setdefault(port, []).append("host process")
                return owners
            except (TypeError, ValueError):
                return owners
        for match in re.finditer(r"(?:[:.]|\s)(\d{1,5})(?:\s|$)", result.stdout or ""):
            port = int(match.group(1))
            if 1 <= port <= 65535:
                owners.setdefault(port, []).append("host process")
        return owners

    def occupied_ports(self) -> dict[int, list[str]]:
        owners: dict[int, list[str]] = {}
        for container in self.list_containers():
            for port in container.ports:
                owners.setdefault(port, []).append(f"container {container.name or container.id[:12]}")
        for port, values in self._fallback_host_ports().items():
            # Docker Desktop exposes the same published port through its host
            # proxy. Docker inspect is authoritative for those ports; adding
            # the proxy as a second owner would make a related SPX stack look
            # like an unrelated conflict and block a safe replacement.
            if port in owners:
                continue
            owners.setdefault(port, []).extend(value for value in values if value not in owners.get(port, []))
        return owners

    def preflight(self, required_ports: Iterable[int] = ()) -> PreflightResult:
        self.check_prerequisites()
        return PreflightResult(
            existing=self.detect_existing_stacks(),
            occupied_ports=self.occupied_ports(),
            required_ports=sorted({int(port) for port in required_ports if int(port) > 0}),
        )

    def describe(self, result: PreflightResult, output: Callable[[str], None] = print) -> None:
        for stack in result.existing:
            images = ", ".join(
                f"{container.name}: {container.image} (health={container.health or 'unknown'})"
                for container in stack.containers
            )
            config = ", ".join(stack.compose_files) or "not reported by Docker"
            ports = ", ".join(str(port) for port in stack.ports) or "none"
            output(
                f"[spx-preflight] Existing stack: project={stack.project}, "
                f"config={config}, ports={ports}\n  {images}"
            )
        for port, owners in result.conflicts.items():
            output(f"[spx-preflight] Port {port} is occupied by: {', '.join(owners)}")

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
            self._run(["docker", "update", "--label-rm", label, container_id], check=False)

    def snapshot_existing(self, stack: ExistingStack, snapshot_path: Path) -> StackSnapshot:
        snapshot = StackSnapshot.empty(self.project, self.installation_id)
        for container in stack.containers:
            if container.running:
                self._run(["docker", "stop", container.id])
            rollback_name = f"spx-rollback-{container.id[:12]}"
            if container.name != rollback_name:
                self._run(["docker", "rename", container.id, rollback_name])
            self._detach_snapshot_container(container.id)
            snapshot.containers.append({"id": container.id, "name": container.name, "rollback_name": rollback_name})
        snapshot.save(snapshot_path)
        return snapshot

    def prepare(
        self,
        snapshot_path: Path,
        *,
        required_ports: Iterable[int] = (),
        assume_yes: bool = False,
        input_fn: Callable[[str], str] = input,
        output: Callable[[str], None] = print,
    ) -> PreflightResult:
        result = self.preflight(required_ports)
        self.describe(result, output)
        active = result.active_stacks
        replaceable = [stack for stack in result.existing if stack.containers]
        if result.unrelated_conflicts:
            raise PreflightError("One or more required ports are occupied by unrelated processes or containers")
        if replaceable:
            if not assume_yes:
                answer = input_fn("[spx-preflight] Replace the detected SPX stack? [y/N]: ").strip().lower()
                if answer not in {"y", "yes"}:
                    raise UserDeclined("Existing SPX stack was left untouched; compose up was not run")
            combined = ExistingStack(
                containers=[container for stack in replaceable for container in stack.containers],
                project=replaceable[0].project,
                compose_files=sorted({path for stack in replaceable for path in stack.compose_files}),
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
        return [container for container in self.list_containers() if container.installation_id == self.installation_id]

    def stop_transaction(self) -> None:
        for container in self.transaction_containers():
            if container.running:
                self._run(["docker", "stop", container.id], check=False)

    def rollback(self, snapshot_path: Path) -> None:
        self.stop_transaction()
        # Current transaction containers still own the compatibility names.
        for container in self.transaction_containers():
            self._run(["docker", "rename", container.id, f"spx-failed-{container.id[:12]}"], check=False)
            self._detach_snapshot_container(container.id)
        if not snapshot_path.exists():
            return
        snapshot = StackSnapshot.load(snapshot_path)
        for entry in snapshot.containers:
            container_id = str(entry.get("id", ""))
            original_name = str(entry.get("name", ""))
            if not container_id or not original_name:
                continue
            result = self._run(["docker", "rename", container_id, original_name], check=False)
            if result.returncode == 0:
                self._run(["docker", "start", container_id], check=False)

    def wait_health(self, api_url: str = "http://localhost:8000", timeout: float = 120.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            containers = self.transaction_containers()
            server = next((item for item in containers if item.name == "spx-server" or item.service == "spx-server"), None)
            if server and server.running and (not server.health or server.health == "healthy") and self._api_healthy(api_url):
                return
            time.sleep(2.0)
        raise StackManagerError(f"SPX healthcheck/API did not become ready within {timeout:.0f} seconds")

    def _api_healthy(self, api_url: str) -> bool:
        try:
            request = urllib.request.Request(api_url.rstrip("/") + "/health", method="GET")
            with urllib.request.urlopen(request, timeout=3.0) as response:
                return 200 <= response.status < 300
        except (OSError, urllib.error.URLError, ValueError):
            return False


def _parse_ports(raw: str) -> list[int]:
    ports: list[int] = []
    for value in (part.strip() for part in raw.split(",")):
        if value.isdigit() and 1 <= int(value) <= 65535:
            ports.append(int(value))
    return sorted(set(ports))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Safely manage an installer-owned SPX Docker stack")
    parser.add_argument("command", choices=["preflight", "prepare", "rollback", "stop", "wait-health"])
    parser.add_argument("--compose-file", required=True)
    parser.add_argument("--env-file", default=None)
    parser.add_argument("--project", default=PROJECT)
    parser.add_argument("--installation-id", default="")
    parser.add_argument("--snapshot", default=".spx-stack-snapshot.json")
    parser.add_argument("--ports", default="")
    parser.add_argument("--yes", action="store_true", help="Accept replacement of an existing stack")
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--timeout", type=float, default=120.0)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manager = StackManager(
        args.compose_file,
        args.env_file,
        project=args.project,
        installation_id=args.installation_id,
    )
    snapshot_path = Path(args.snapshot)
    if args.command == "preflight":
        result = manager.preflight(_parse_ports(args.ports))
        manager.describe(result)
        if result.unrelated_conflicts:
            raise PreflightError("Required ports are already occupied")
        return 0
    if args.command == "prepare":
        manager.prepare(snapshot_path, required_ports=_parse_ports(args.ports), assume_yes=args.yes)
        return 0
    if args.command == "rollback":
        manager.rollback(snapshot_path)
        return 0
    if args.command == "stop":
        manager.stop_transaction()
        return 0
    if args.command == "wait-health":
        manager.wait_health(args.api_url, args.timeout)
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
