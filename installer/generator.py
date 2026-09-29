# SPDX-License-Identifier: MIT
"""Generate deployment artifacts (docker-compose, helper scripts, env files)."""

from __future__ import annotations

import copy
import filecmp
import json
import os
import re
import shutil
import sys
import uuid
import stat
from pathlib import Path
from typing import Dict, List, Set

import yaml

from .manifest import ManifestIndex, ServiceManifest
from . import paths
from .compatibility import SPX_SERVER_VERSION, SPX_UI_VERSION, validate_version_pair
from .telemetry import resolve_telemetry_environment, write_telemetry_manifest


SPX_SERVER_SERVICE_NAME = "spx-server"
SPX_SERVER_IMAGE = f"simplephysx/spx-server:{SPX_SERVER_VERSION}"
# SPX_SERVER_IMAGE = "spx-server:trial"
SPX_UI_SERVICE_NAME = "spx-ui"
SPX_UI_IMAGE = f"simplephysx/spx-ui:{SPX_UI_VERSION}"

SPX_COMPOSE_PROJECT = "spx"
SPX_LABEL_STACK = "com.simplephysx.spx.stack"
SPX_LABEL_MANAGED_BY = "com.simplephysx.spx.managed-by"
SPX_LABEL_PROJECT = "com.simplephysx.spx.project"
SPX_LABEL_INSTALLATION_ID = "com.simplephysx.spx.installation-id"
MODBUS_GATEWAY_PORT = 502
MODBUS_INSTANCE_PORT_START = 5020
MODBUS_INSTANCE_PORT_END = 5120


class DeploymentGenerator:
    """Create runnable artifacts from wizard selections."""

    def __init__(self, index: ManifestIndex) -> None:
        self.index = index
        self.repo_root = paths.repo_root()
        self.telemetry_environment = resolve_telemetry_environment(
            self.repo_root / "installer"
        )
        validate_version_pair(SPX_SERVER_VERSION, SPX_UI_VERSION)

    def generate(self, selection, output_dir: Path) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        spx_python_requirement = self._resolve_spx_python_requirement()

        installation_id = uuid.uuid4().hex

        assets_root = output_dir / "assets"
        assets_root.mkdir(parents=True, exist_ok=True)

        # Bundle local extensions so generated artifacts remain self-contained.
        extensions_src = self.repo_root / "extensions"
        if extensions_src.exists():
            shutil.copytree(
                extensions_src, output_dir / "extensions", dirs_exist_ok=True
            )

        compose_data = self._build_compose(
            selection.service_ids,
            assets_root,
            selection.install_spx_ui,
            installation_id=installation_id,
            service_bind_addresses=getattr(selection, "service_bind_addresses", {}),
            telemetry_environment=self.telemetry_environment,
        )
        compose_path = output_dir / "docker-compose.generated.yml"
        with compose_path.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(compose_data, handle, sort_keys=False)

        write_telemetry_manifest(
            output_dir,
            selection,
            installation_id=installation_id,
            repo_root=self.repo_root,
        )

        self._write_env(
            output_dir,
            selection.license_key,
            selection.service_ids,
            getattr(selection, "service_bind_addresses", {}),
        )
        self._write_bundle(
            output_dir,
            selection,
            installation_id=installation_id,
            compose_data=compose_data,
            spx_python_requirement=spx_python_requirement,
        )
        self._write_hardened_artifacts(
            output_dir,
            installation_id,
            compose_data,
            spx_python_requirement,
        )
        return

    # Internal helpers -------------------------------------------------------
    def _build_compose(
        self,
        service_ids: List[str],
        assets_root: Path,
        include_ui: bool,
        *,
        installation_id: str = "",
        service_bind_addresses: Dict[str, str] | None = None,
        telemetry_environment: str = "staging",
    ) -> Dict[str, Dict]:
        services: Dict[str, Dict] = {}
        builtin_ports: List[str] = []
        docker_services: Dict[str, ServiceManifest] = {}
        native_services: List[ServiceManifest] = []
        modbus_enabled = False
        service_bind_addresses = service_bind_addresses or {}

        for service_id in service_ids:
            manifest = self.index.services.get(service_id)
            if not manifest or not manifest.deployment:
                continue
            runtime = manifest.deployment.runtime
            bind_expression = self._bind_expression(
                manifest,
                service_bind_addresses.get(service_id, "127.0.0.1"),
            )
            if runtime == "builtin":
                builtin_ports.extend(self._format_ports(manifest, bind_expression))
            elif runtime == "docker":
                docker_services[service_id] = manifest
            else:
                native_services.append(manifest)
            if service_id == "modbus_tcp_gateway":
                modbus_enabled = True

        if modbus_enabled:
            # Expose an extended Modbus TCP range for multi-instance demos.
            bind_expression = self._bind_expression(
                self.index.services["modbus_tcp_gateway"],
                service_bind_addresses.get("modbus_tcp_gateway", "127.0.0.1"),
            )
            builtin_ports.extend(
                [
                    f"{bind_expression}:{port}:{port}"
                    for port in range(
                        MODBUS_INSTANCE_PORT_START, MODBUS_INSTANCE_PORT_END + 1
                    )
                ]
            )

        labels = self._stack_labels(installation_id)
        services[SPX_SERVER_SERVICE_NAME] = self._build_spx_server_service(
            builtin_ports,
            assets_root,
            labels,
            telemetry_environment=telemetry_environment,
        )
        if include_ui:
            services[SPX_UI_SERVICE_NAME] = self._build_spx_ui_service(labels)

        for service_id, manifest in docker_services.items():
            bind_expression = self._bind_expression(
                manifest,
                service_bind_addresses.get(service_id, "127.0.0.1"),
            )
            services[service_id] = self._build_docker_service(
                manifest, assets_root, labels, bind_expression
            )

        compose = {
            "name": SPX_COMPOSE_PROJECT,
            "services": services,
        }
        if native_services:
            compose.setdefault("x-native-services", [])  # hint for future steps
            compose["x-native-services"] = [svc.id for svc in native_services]
        return compose

    def _stack_labels(self, installation_id: str) -> Dict[str, str]:
        return {
            SPX_LABEL_STACK: "true",
            SPX_LABEL_MANAGED_BY: "installer",
            SPX_LABEL_PROJECT: SPX_COMPOSE_PROJECT,
            SPX_LABEL_INSTALLATION_ID: installation_id or uuid.uuid4().hex,
        }

    def _build_spx_server_service(
        self,
        extra_ports: List[str],
        assets_root: Path,
        labels: Dict[str, str] | None = None,
        *,
        telemetry_environment: str = "staging",
    ) -> Dict:
        ports = ["8000:8000"]
        for port in extra_ports:
            if port not in ports:
                ports.append(port)

        volumes = [
            self._process_volume("./extensions:/app/extensions", assets_root),
            "./telemetry.json:/app/telemetry.json:ro",
        ]
        service = {
            "image": SPX_SERVER_IMAGE,
            "container_name": "spx-server",
            "labels": dict(labels or self._stack_labels("")),
            # Ensure host.docker.internal resolves on Linux (Docker Engine) for models
            # that reference host-mapped service ports (e.g., MQTT, LwM2M, BLE bridge).
            "extra_hosts": ["host.docker.internal:host-gateway"],
            "ports": ports,
            "environment": {
                "SPX_PRODUCT_KEY": "${SPX_PRODUCT_KEY}",
                "SPX_TELEMETRY_ENVIRONMENT": telemetry_environment,
                "SPX_TELEMETRY_MANIFEST_PATH": "/app/telemetry.json",
            },
            "healthcheck": {
                "test": [
                    "CMD",
                    "python",
                    "-c",
                    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)",
                ],
                "interval": "10s",
                "timeout": "5s",
                "retries": 5,
            },
            "volumes": volumes,
            "command": [
                "--address",
                "0.0.0.0",
                "--product-key",
                "${SPX_PRODUCT_KEY}",
                "--extensions",
                "/app/extensions",
            ],
        }
        return service

    def _build_spx_ui_service(self, labels: Dict[str, str] | None = None) -> Dict:
        return {
            "image": SPX_UI_IMAGE,
            "container_name": "spx-ui-server",
            "labels": dict(labels or self._stack_labels("")),
            "depends_on": {
                SPX_SERVER_SERVICE_NAME: {
                    "condition": "service_healthy",
                }
            },
            "ports": ["3000:3000"],
            "environment": {
                "SPX_PRODUCT_KEY": "${SPX_PRODUCT_KEY}",
            },
        }

    def _build_docker_service(
        self,
        manifest: ServiceManifest,
        assets_root: Path,
        labels: Dict[str, str] | None = None,
        bind_expression: str | None = None,
    ) -> Dict:
        deployment = manifest.deployment
        assert deployment is not None
        service = {
            "image": deployment.image,
            "container_name": deployment.container_name or manifest.id,
            "labels": dict(labels or self._stack_labels("")),
        }
        ports = self._format_ports(manifest, bind_expression)
        if ports:
            service["ports"] = ports
        if deployment.volumes:
            service["volumes"] = [
                self._process_volume(entry, assets_root) for entry in deployment.volumes
            ]
        if deployment.environment:
            service["environment"] = deployment.environment
        if deployment.entrypoint:
            service["entrypoint"] = deployment.entrypoint
        if deployment.command:
            service["command"] = deployment.command
        if deployment.restart:
            service["restart"] = deployment.restart
        if deployment.depends_on:
            service["depends_on"] = deployment.depends_on
        if deployment.hostname:
            service["hostname"] = deployment.hostname
        return service

    @staticmethod
    def _bind_env_name(service_id: str) -> str:
        return "SPX_BIND_" + re.sub(r"[^A-Za-z0-9]", "_", service_id).upper()

    def _bind_expression(self, manifest: ServiceManifest, default: str) -> str:
        bind_variable = f"${{{self._bind_env_name(manifest.id)}:-{default}}}"
        if manifest.id == "bacnet_gateway":
            # Keep the pre-existing manual setting usable by existing bundles.
            return f"${{BACNET_BIND_ADDR:-{bind_variable}}}"
        return bind_variable

    def _format_ports(
        self, manifest: ServiceManifest, bind_expression: str | None = None
    ) -> List[str]:
        entries = []
        bind_expression = bind_expression or self._bind_expression(
            manifest, "127.0.0.1"
        )
        for port in manifest.ports:
            transport = port.transport.lower()
            if transport == "udp":
                entry = f"{bind_expression}:{port.host}:{port.container}/udp"
            else:
                entry = f"{bind_expression}:{port.host}:{port.container}"
            entries.append(entry)
        return entries

    def _process_volume(self, entry: str, assets_root: Path) -> str:
        if not entry:
            return entry
        parts = entry.split(":")
        if len(parts) < 2:
            return entry
        host = parts[0]
        rest = ":".join(parts[1:])
        new_host = self._relocate_host_path(host, assets_root)
        return f"{new_host}:{rest}" if rest else new_host

    def _relocate_host_path(self, host: str, assets_root: Path) -> str:
        clean = host

        if host.startswith("./"):
            clean = host[2:]
        else:
            clean = host

        relative = None
        if clean.startswith("library/assets/"):
            relative = clean[len("library/assets/") :]
        elif clean.startswith("docker/"):
            relative = clean[len("docker/") :]

        if relative is None:
            return host

        src = self.repo_root / clean
        if not src.exists():
            return host

        dest = assets_root / relative
        if src.is_dir():
            shutil.copytree(src, dest, dirs_exist_ok=True)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.is_symlink():
                raise IsADirectoryError(
                    f"Refusing to replace symlink at generated asset path: {dest}"
                )
            if dest.is_dir():
                # Repeated generation can leave a directory where a file is
                # expected (for example knxd.ini/knxd.ini). Repair only the
                # exact, byte-identical nested copy; preserve other contents.
                entries = list(dest.iterdir())
                nested_copy = dest / src.name
                if not entries:
                    dest.rmdir()
                elif (
                    len(entries) == 1
                    and entries[0] == nested_copy
                    and nested_copy.is_file()
                    and filecmp.cmp(src, nested_copy, shallow=False)
                ):
                    nested_copy.unlink()
                    dest.rmdir()
                else:
                    raise IsADirectoryError(
                        f"Generated asset path is a directory with unexpected contents: {dest}"
                    )
            shutil.copy2(src, dest)

        return f"./assets/{relative}"

    def _write_env(
        self,
        output_dir: Path,
        product_key: str,
        service_ids: List[str] | None = None,
        service_bind_addresses: Dict[str, str] | None = None,
    ) -> None:
        env_path = output_dir / ".env"
        value = product_key or "REPLACE_ME"
        lines = [f"SPX_PRODUCT_KEY={value}"]
        for service_id in service_ids or []:
            manifest = self.index.services.get(service_id)
            deployment = manifest.deployment if manifest is not None else None
            if (
                manifest is None
                or not manifest.ports
                or manifest.network_exposure != "selectable"
                or deployment is None
                or deployment.runtime not in {"builtin", "docker"}
            ):
                continue
            address = (service_bind_addresses or {}).get(service_id, "127.0.0.1")
            lines.append(f"{self._bind_env_name(service_id)}={address}")
        env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _write_script(self, path: Path, command: str) -> None:
        script = "#!/usr/bin/env bash\nset -euo pipefail\n" + command
        path.write_text(script, encoding="utf-8")
        mode = os.stat(path).st_mode
        os.chmod(path, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    def _write_ps_script(self, path: Path, command: str) -> None:
        try:
            path.write_text(command, encoding="utf-8")
        except PermissionError:
            if os.name != "nt":
                raise
            print(
                f"[spx-installer] Windows denied writing the optional PowerShell "
                f"launcher '{path.name}'. Continuing; use the matching .bat "
                "launcher. Check Windows Security or endpoint-protection logs "
                "if you need the PowerShell wrapper.",
                file=sys.stderr,
            )

    def _write_text_script(
        self, path: Path, command: str, *, executable: bool = False
    ) -> None:
        path.write_text(command, encoding="utf-8")
        if executable:
            mode = os.stat(path).st_mode
            os.chmod(path, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    def _compose_host_ports(self, compose_data: Dict[str, Dict]) -> List[int]:
        ports: Set[int] = set()
        for service in compose_data.get("services", {}).values():
            for entry in service.get("ports", []) or []:
                raw = str(entry).split("/")[0]
                parts = raw.split(":")
                candidate = (
                    parts[0]
                    if len(parts) == 2
                    else parts[-2] if len(parts) >= 3 else ""
                )
                digits = "".join(char for char in candidate if char.isdigit())
                if digits and 1 <= int(digits) <= 65535:
                    ports.add(int(digits))
        return sorted(ports)

    def _write_hardened_artifacts(
        self,
        output_dir: Path,
        installation_id: str,
        compose_data: Dict[str, Dict],
        spx_python_requirement: str,
    ) -> None:
        """Write the transactional scripts used by every generated bundle."""

        shutil.copy2(
            Path(__file__).with_name("stack_manager.py"),
            output_dir / "stack_manager.py",
        )
        shutil.copy2(
            Path(__file__).with_name("stack_runner.py"), output_dir / "stack_runner.py"
        )
        shutil.copy2(Path(__file__).with_name("network.py"), output_dir / "network.py")
        shutil.copy2(
            Path(__file__).with_name("modbus_port_configurator.py"),
            output_dir / "modbus_port_configurator.py",
        )
        shutil.copy2(
            Path(__file__).with_name("bootstrap.py"), output_dir / "bootstrap_runner.py"
        )
        self._write_runtime_bootstrap(output_dir)
        self._write_macos_python_helper(output_dir)

        # Compose cannot remove labels from an existing container. Starting a
        # replacement under transaction-only names prevents Compose from
        # adopting the old, snapshotted containers that still carry the old
        # project metadata. StackManager renames these exact containers to the
        # stable service names only after the transaction has succeeded.
        transaction_compose = copy.deepcopy(compose_data)
        final_name_pairs: list[tuple[str, str]] = []
        transaction_services: dict[str, dict] = {}
        service_names = list((transaction_compose.get("services", {}) or {}).keys())
        transaction_service_names = {
            service_name: f"transaction-__TRANSACTION_TOKEN__-{service_name}"
            for service_name in service_names
        }
        for service_name in service_names:
            service = transaction_compose["services"][service_name]
            final_name = str(service.get("container_name", service_name))
            transaction_service_name = transaction_service_names[service_name]
            transaction_name = f"spx-transaction-__TRANSACTION_TOKEN__-{service_name}"
            service["container_name"] = transaction_name
            # Transaction-prefixed service keys are only isolation names. Keep
            # the original Compose DNS name available to models that connect
            # to bundled services by their stable ID (for example knx_gateway).
            networks = service.setdefault("networks", {})
            default_network = networks.setdefault("default", {})
            aliases = default_network.setdefault("aliases", [])
            if service_name not in aliases:
                aliases.append(service_name)
            depends_on = service.get("depends_on")
            if isinstance(depends_on, dict):
                service["depends_on"] = {
                    transaction_service_names.get(dependency, dependency): condition
                    for dependency, condition in depends_on.items()
                }
            elif isinstance(depends_on, list):
                service["depends_on"] = [
                    transaction_service_names.get(dependency, dependency)
                    for dependency in depends_on
                ]
            transaction_services[transaction_service_name] = service
            final_name_pairs.append((service_name, final_name))
        transaction_compose["services"] = transaction_services
        with (output_dir / "docker-compose.transaction.yml").open(
            "w", encoding="utf-8"
        ) as handle:
            yaml.safe_dump(transaction_compose, handle, sort_keys=False)

        final_name_bash = "\n".join(
            f'  "--final-name" "{service_name}={final_name}"'
            for service_name, final_name in final_name_pairs
        )
        bash = (
            r"""SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MACOS_PYTHON_HELPER="${SCRIPT_DIR}/macos_python_runtime.sh"
if [ "$(uname -s)" = "Darwin" ] && [ -f "${MACOS_PYTHON_HELPER}" ]; then
  # shellcheck source=/dev/null
  . "${MACOS_PYTHON_HELPER}"
fi
INSTALLATION_ID="__INSTALLATION_ID__"
SNAPSHOT="$SCRIPT_DIR/.spx-stack-snapshot.json"
MANAGER="$SCRIPT_DIR/stack_manager.py"
TRANSACTION_COMPOSE_TEMPLATE="$SCRIPT_DIR/docker-compose.transaction.yml"
TRANSACTION_TOKEN="$(date +%s)-$$"
STAGED_PORTS_FILE="$SCRIPT_DIR/.spx-modbus-ports.pending-${TRANSACTION_TOKEN}.json"
TRANSACTION_COMPOSE="$SCRIPT_DIR/.docker-compose.transaction.${TRANSACTION_TOKEN}.yml"
TRANSACTION_UI_SERVICE="transaction-${TRANSACTION_TOKEN}-spx-ui"
STAGE="runtime"
# The installer launcher and the generated stack deliberately use different
# environment variables. PYTHON_BIN may point at the installer's private
# runtime, including a path with spaces, and must never be inherited here.
SYSTEM_PYTHON_BIN="${SPX_SYSTEM_PYTHON_BIN:-}"
RUNTIME_PYTHON_BIN=""
BLE_ADAPTER_PID=""
TRANSACTION_PREPARED=0

if [ -z "$SYSTEM_PYTHON_BIN" ]; then
  if command -v spx_resolve_macos_python >/dev/null 2>&1; then
    SYSTEM_PYTHON_BIN="$(spx_resolve_macos_python || true)"
  fi
fi

if [ -z "$SYSTEM_PYTHON_BIN" ]; then
  if command -v python3 >/dev/null 2>&1; then
    SYSTEM_PYTHON_BIN=python3
  elif command -v python >/dev/null 2>&1; then
    SYSTEM_PYTHON_BIN=python
  else
    echo "[spx-start] stage=runtime: missing Python 3" >&2
    exit 1
  fi
fi

PREPARE_ARGS=(
  "prepare"
  "--compose-file" "$SCRIPT_DIR/docker-compose.generated.yml"
  "--env-file" "$SCRIPT_DIR/.env"
  "--project" "spx"
  "--installation-id" "$INSTALLATION_ID"
  "--snapshot" "$SNAPSHOT"
)
FINAL_NAME_ARGS=(
__FINAL_NAME_BASH__
)
for arg in "$@"; do
  if [ "$arg" = "--yes" ]; then
    PREPARE_ARGS+=("--yes")
  fi
done

cleanup_on_failure() {
  local status=$?
  trap - ERR INT TERM
  if [ "$TRANSACTION_PREPARED" -eq 1 ]; then
    echo "[spx-start] stage=${STAGE}: installation failed (exit code ${status}); attempting rollback" >&2
  else
    echo "[spx-start] stage=${STAGE}: installation failed (exit code ${status})" >&2
  fi
  if [ -n "${BLE_ADAPTER_PID:-}" ] && kill -0 "$BLE_ADAPTER_PID" >/dev/null 2>&1; then
    kill "$BLE_ADAPTER_PID" >/dev/null 2>&1 || true
  fi
  if [ "$TRANSACTION_PREPARED" -eq 1 ] && [ -n "$RUNTIME_PYTHON_BIN" ] && { [ -x "$MANAGER" ] || [ -f "$MANAGER" ]; }; then
    "$RUNTIME_PYTHON_BIN" "$MANAGER" rollback \
      --compose-file "$SCRIPT_DIR/docker-compose.generated.yml" \
      --env-file "$SCRIPT_DIR/.env" \
      --project spx \
      --installation-id "$INSTALLATION_ID" \
      --snapshot "$SNAPSHOT" >/dev/null 2>&1 || \
      echo "[spx-start] stage=rollback: automatic restore was not completed" >&2
  fi
  if [ -n "${TRANSACTION_COMPOSE:-}" ]; then
    rm -f "$TRANSACTION_COMPOSE" >/dev/null 2>&1 || true
  fi
  rm -f "$STAGED_PORTS_FILE" >/dev/null 2>&1 || true
  exit "$status"
}
trap cleanup_on_failure ERR INT TERM

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "[spx-start] stage=${STAGE}: missing required command: $1" >&2
    exit 1
  fi
}

need_cmd docker
need_cmd "$SYSTEM_PYTHON_BIN"
if [ ! -f "$SCRIPT_DIR/runtime_bootstrap.py" ]; then
  echo "[spx-start] stage=runtime: missing runtime bootstrap helper" >&2
  exit 1
fi
RUNTIME_PYTHON_BIN="$("$SYSTEM_PYTHON_BIN" "$SCRIPT_DIR/runtime_bootstrap.py" \
  --venv-dir "$SCRIPT_DIR/.spx-runtime" \
  --package requests \
  --package "__SPX_PYTHON_REQUIREMENT__" \
  --package pyyaml)"
if [ -z "$RUNTIME_PYTHON_BIN" ] || [ ! -x "$RUNTIME_PYTHON_BIN" ]; then
  echo "[spx-start] stage=runtime: local Python runtime bootstrap failed" >&2
  exit 1
fi
if [ ! -f "$TRANSACTION_COMPOSE_TEMPLATE" ]; then
  echo "[spx-start] stage=runtime: missing transaction Compose template" >&2
  exit 1
fi
if "$RUNTIME_PYTHON_BIN" - "$SCRIPT_DIR/bundle.json" <<'PY'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as handle:
    raise SystemExit(0 if "btvirt_adapter" in json.load(handle).get("services", []) else 1)
PY
then
  if command -v npm >/dev/null 2>&1 && command -v spx-ble-adapter >/dev/null 2>&1; then
    spx-ble-adapter --port "${BLE_ADAPTER_PORT:-8085}" >/dev/null 2>&1 &
    BLE_ADAPTER_PID=$!
  elif command -v npm >/dev/null 2>&1; then
    npm install -g @simplephysx/spx-ble-adapter >/dev/null 2>&1
    spx-ble-adapter --port "${BLE_ADAPTER_PORT:-8085}" >/dev/null 2>&1 &
    BLE_ADAPTER_PID=$!
  else
    echo "[spx-start] stage=runtime: npm is unavailable; BLE adapter was not started" >&2
  fi
fi

STAGE="preflight"
"$RUNTIME_PYTHON_BIN" "$SCRIPT_DIR/modbus_port_configurator.py" stage \
  --compose-file "$SCRIPT_DIR/docker-compose.generated.yml" \
  --bundle "$SCRIPT_DIR/bundle.json" \
  --env-file "$SCRIPT_DIR/.env" \
  --staged-file "$STAGED_PORTS_FILE"
REQUIRED_PORTS="$("$RUNTIME_PYTHON_BIN" "$SCRIPT_DIR/modbus_port_configurator.py" required-ports \
  --staged-file "$STAGED_PORTS_FILE")"
PREPARE_ARGS+=("--ports" "$REQUIRED_PORTS")
"$RUNTIME_PYTHON_BIN" "$SCRIPT_DIR/network.py" --env-file "$SCRIPT_DIR/.env" --published-ports "$REQUIRED_PORTS"
"$RUNTIME_PYTHON_BIN" "$MANAGER" "${PREPARE_ARGS[@]}"
TRANSACTION_PREPARED=1
"$RUNTIME_PYTHON_BIN" "$SCRIPT_DIR/modbus_port_configurator.py" commit \
  --compose-file "$SCRIPT_DIR/docker-compose.generated.yml" \
  --transaction-template "$TRANSACTION_COMPOSE_TEMPLATE" \
  --bundle "$SCRIPT_DIR/bundle.json" \
  --staged-file "$STAGED_PORTS_FILE"
rm -f "$STAGED_PORTS_FILE" >/dev/null 2>&1 || true
sed "s/__TRANSACTION_TOKEN__/${TRANSACTION_TOKEN}/g" "$TRANSACTION_COMPOSE_TEMPLATE" > "$TRANSACTION_COMPOSE"

STAGE="compose"
docker compose -p spx -f "$TRANSACTION_COMPOSE" --env-file "$SCRIPT_DIR/.env" up -d

STAGE="healthcheck"
"$RUNTIME_PYTHON_BIN" "$MANAGER" wait-health \
  --compose-file "$SCRIPT_DIR/docker-compose.generated.yml" \
  --env-file "$SCRIPT_DIR/.env" \
  --project spx \
  --installation-id "$INSTALLATION_ID" \
  --api-url "${SPX_BASE_URL:-http://localhost:8000}"

if [ "__UI_ENABLED__" = "yes" ]; then
  STAGE="ui"
  if ! docker compose -p spx -f "$TRANSACTION_COMPOSE" --env-file "$SCRIPT_DIR/.env" ps --services --status running | grep -Fxq "$TRANSACTION_UI_SERVICE"; then
    echo "[spx-start] stage=ui: SPX UI is not running" >&2
    exit 1
  fi
fi

STAGE="bootstrap"
"$RUNTIME_PYTHON_BIN" "$SCRIPT_DIR/bootstrap_runner.py" \
  --bundle "$SCRIPT_DIR/bundle.json" \
  --api-url "${SPX_BASE_URL:-http://localhost:8000}"

STAGE="start"
RUNNING_SERVICES="$(docker compose -p spx -f "$TRANSACTION_COMPOSE" --env-file "$SCRIPT_DIR/.env" ps --services --status running)" || {
  echo "[spx-start] stage=start: could not inspect running services" >&2
  exit 1
}
if [ -z "$RUNNING_SERVICES" ]; then
  echo "[spx-start] stage=start: no selected SPX services are running" >&2
  exit 1
fi
RUNNING_SERVICE_LIST="$(printf '%s\n' "$RUNNING_SERVICES" | awk '{ sub(/^transaction-[0-9]+-[0-9]+-/, ""); if (NR > 1) printf ", "; printf "%s", $0 } END { print "" }')"
echo "[spx-start] Running services: ${RUNNING_SERVICE_LIST}"

STAGE="commit"
"$RUNTIME_PYTHON_BIN" "$MANAGER" commit \
  --compose-file "$SCRIPT_DIR/docker-compose.generated.yml" \
  --env-file "$SCRIPT_DIR/.env" \
  --project spx \
  --installation-id "$INSTALLATION_ID" \
  --snapshot "$SNAPSHOT" \
  "${FINAL_NAME_ARGS[@]}"
rm -f "$TRANSACTION_COMPOSE" >/dev/null 2>&1 || true

echo ""
echo "[spx-start] SPX started successfully."
echo "[spx-start] UI: http://localhost:3000 (if enabled), API: http://localhost:8000"
"$RUNTIME_PYTHON_BIN" "$SCRIPT_DIR/modbus_port_configurator.py" summary \
  --bundle "$SCRIPT_DIR/bundle.json" \
  --compose-file "$SCRIPT_DIR/docker-compose.generated.yml" || true
""".replace(
                "__INSTALLATION_ID__", installation_id
            )
            .replace("__SPX_PYTHON_REQUIREMENT__", spx_python_requirement)
            .replace("__FINAL_NAME_BASH__", final_name_bash)
        )
        ui_enabled = SPX_UI_SERVICE_NAME in (compose_data.get("services", {}) or {})
        self._write_script(
            output_dir / "spx-start.sh",
            bash.replace("__UI_ENABLED__", "yes" if ui_enabled else "no").strip()
            + "\n",
        )

        powershell = r"""[CmdletBinding()]
param([switch]$Yes)
$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Launcher = Join-Path $ScriptDir '..\app\SpxLauncher.exe'
$RunnerArgs = @((Join-Path $ScriptDir 'stack_runner.py'), 'start')
$LauncherArgs = @('start')
if ($Yes) { $RunnerArgs += '--yes' }
if ($Yes) { $LauncherArgs += '--yes' }
if (Test-Path $Launcher) {
    & $Launcher @LauncherArgs
} elseif ($Env:SPX_SYSTEM_PYTHON_BIN) {
    & $Env:SPX_SYSTEM_PYTHON_BIN @RunnerArgs
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 @RunnerArgs
} elseif (Get-Command python3 -ErrorAction SilentlyContinue) {
    & python3 @RunnerArgs
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    & python @RunnerArgs
} else {
    Write-Error 'Python 3 was not found. Install Python 3 or use the SPX Tools launcher.'
    exit 1
}
exit $LASTEXITCODE
"""
        self._write_ps_script(output_dir / "spx-start.ps1", powershell)

        stop_sh = r"""SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MACOS_PYTHON_HELPER="${SCRIPT_DIR}/macos_python_runtime.sh"
if [ "$(uname -s)" = "Darwin" ] && [ -f "${MACOS_PYTHON_HELPER}" ]; then
  # shellcheck source=/dev/null
  . "${MACOS_PYTHON_HELPER}"
fi
SYSTEM_PYTHON_BIN="${SPX_SYSTEM_PYTHON_BIN:-}"
if [ -z "$SYSTEM_PYTHON_BIN" ] && command -v spx_resolve_macos_python >/dev/null 2>&1; then
  SYSTEM_PYTHON_BIN="$(spx_resolve_macos_python || true)"
fi
if [ -z "$SYSTEM_PYTHON_BIN" ]; then
  SYSTEM_PYTHON_BIN="$(command -v python3 || command -v python || true)"
fi
if [ -z "$SYSTEM_PYTHON_BIN" ]; then
  echo "[spx-stop] Python 3 is required to stop the generated stack." >&2
  exit 1
fi
exec "$SYSTEM_PYTHON_BIN" "$SCRIPT_DIR/stack_manager.py" stop \
  --compose-file "$SCRIPT_DIR/docker-compose.generated.yml" \
  --env-file "$SCRIPT_DIR/.env" \
  --project spx \
  --installation-id "__INSTALLATION_ID__"
""".replace(
            "__INSTALLATION_ID__", installation_id
        )
        self._write_script(output_dir / "spx-stop.sh", stop_sh.strip() + "\n")
        stop_ps = r"""$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Launcher = Join-Path $ScriptDir '..\app\SpxLauncher.exe'
$RunnerArgs = @((Join-Path $ScriptDir 'stack_runner.py'), 'stop')
if (Test-Path $Launcher) {
    & $Launcher stop
} elseif ($Env:SPX_SYSTEM_PYTHON_BIN) {
    & $Env:SPX_SYSTEM_PYTHON_BIN @RunnerArgs
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 @RunnerArgs
} elseif (Get-Command python3 -ErrorAction SilentlyContinue) {
    & python3 @RunnerArgs
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    & python @RunnerArgs
} else {
    Write-Error 'Python 3 was not found. Install Python 3 or use the SPX Tools launcher.'
    exit 1
}
exit $LASTEXITCODE
"""
        self._write_ps_script(output_dir / "spx-stop.ps1", stop_ps.strip() + "\n")

        start_command = """#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec bash "$SCRIPT_DIR/spx-start.sh" "$@"
"""
        stop_command = """#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec bash "$SCRIPT_DIR/spx-stop.sh" "$@"
"""
        start_bat = r"""@echo off
setlocal
if exist "%~dp0..\app\SpxLauncher.exe" goto run_native
where py >nul 2>nul
if not errorlevel 1 goto run_py
where python3 >nul 2>nul
if not errorlevel 1 goto run_python3
where python >nul 2>nul
if not errorlevel 1 goto run_python
echo Python 3 is required to start the SPX stack.
exit /b 1
:run_native
"%~dp0..\app\SpxLauncher.exe" start %*
exit /b %ERRORLEVEL%
:run_py
py -3 "%~dp0stack_runner.py" start %*
exit /b %ERRORLEVEL%
:run_python3
python3 "%~dp0stack_runner.py" start %*
exit /b %ERRORLEVEL%
:run_python
python "%~dp0stack_runner.py" start %*
exit /b %ERRORLEVEL%
"""
        stop_bat = r"""@echo off
setlocal
if exist "%~dp0..\app\SpxLauncher.exe" goto run_native
where py >nul 2>nul
if not errorlevel 1 goto run_py
where python3 >nul 2>nul
if not errorlevel 1 goto run_python3
where python >nul 2>nul
if not errorlevel 1 goto run_python
echo Python 3 is required to stop the SPX stack.
exit /b 1
:run_native
"%~dp0..\app\SpxLauncher.exe" stop %*
exit /b %ERRORLEVEL%
:run_py
py -3 "%~dp0stack_runner.py" stop %*
exit /b %ERRORLEVEL%
:run_python3
python3 "%~dp0stack_runner.py" stop %*
exit /b %ERRORLEVEL%
:run_python
python "%~dp0stack_runner.py" stop %*
exit /b %ERRORLEVEL%
"""
        self._write_text_script(
            output_dir / "spx-start.command", start_command, executable=True
        )
        self._write_text_script(
            output_dir / "spx-stop.command", stop_command, executable=True
        )
        self._write_text_script(output_dir / "spx-start.bat", start_bat)
        self._write_text_script(output_dir / "spx-stop.bat", stop_bat)

    def _write_bundle(
        self,
        output_dir: Path,
        selection,
        *,
        installation_id: str = "",
        compose_data: Dict[str, Dict] | None = None,
        spx_python_requirement: str = "spx-python",
    ) -> None:
        model_entries = []
        model_paths: Set[Path] = set()
        for model_id in selection.model_ids:
            model = self.index.models[model_id]
            model_path = Path(model.path)
            model_entries.append(
                {
                    "id": model_id,
                    "path": str(model_path),
                }
            )
            model_paths.add(model_path)

        bundle = {
            "packages": selection.packages,
            "protocols": selection.protocols,
            "server_version": SPX_SERVER_VERSION,
            "ui_version": SPX_UI_VERSION,
            "models": model_entries,
            "instances": self._collect_instances(selection),
            "start_instances": list(selection.start_instances),
            "services": selection.service_ids,
            "installation_id": installation_id,
            "compose_project": SPX_COMPOSE_PROJECT,
            "required_ports": self._compose_host_ports(compose_data or {}),
            "spx_python_requirement": spx_python_requirement,
            "final_container_names": [
                f"{service_name}={str(service.get('container_name', service_name))}"
                for service_name, service in (compose_data or {})
                .get("services", {})
                .items()
            ],
            "ui_enabled": SPX_UI_SERVICE_NAME
            in (compose_data or {}).get("services", {}),
        }
        if "modbus_tcp_gateway" in bundle["services"]:
            bundle["modbus_port_mappings"] = {
                "gateway_host_port": MODBUS_GATEWAY_PORT,
                "gateway_container_port": MODBUS_GATEWAY_PORT,
                "instance_host_port_start": MODBUS_INSTANCE_PORT_START,
                "instance_host_port_end": MODBUS_INSTANCE_PORT_END,
                "instance_container_port_start": MODBUS_INSTANCE_PORT_START,
                "instance_port_count": MODBUS_INSTANCE_PORT_END
                - MODBUS_INSTANCE_PORT_START
                + 1,
            }
        bundle_path = output_dir / "bundle.json"
        bundle_path.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
        self._copy_model_sources(model_paths, output_dir)

    def _collect_instances(self, selection) -> list[dict[str, str]]:
        return list(selection.instances)

    def _copy_model_sources(self, model_paths: Set[Path], output_dir: Path) -> None:
        for rel in model_paths:
            src = self.repo_root / rel
            if not src.exists():
                continue
            dest = output_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)

    def _resolve_spx_python_requirement(self) -> str:
        pyproject = self.repo_root / "pyproject.toml"
        if not pyproject.exists():
            return "spx-python"

        content = pyproject.read_text(encoding="utf-8")
        match = re.search(
            r'^\s*spx-python\s*=\s*"([^"]+)"', content, flags=re.MULTILINE
        )
        if not match:
            return "spx-python"

        spec = match.group(1).strip()
        if not spec or any(char in spec for char in "^~<>*,[]"):
            return "spx-python"
        return f"spx-python=={spec}"

    def _write_bootstrap_runner(self, output_dir: Path) -> None:
        # Keep one canonical implementation.  The legacy inline runner below
        # is intentionally unreachable and can be removed after downstream
        # callers stop invoking this private compatibility hook.
        shutil.copy2(
            Path(__file__).with_name("bootstrap.py"), output_dir / "bootstrap_runner.py"
        )
        return

        runner = """#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
\"\"\"Local bootstrap runner bundled with generated artifacts.\"\"\"

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

import requests
import yaml

try:
    import spx_python
except Exception:  # pragma: no cover
    spx_python = None

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_API = os.environ.get("SPX_BASE_URL", "http://localhost:8000")


def load_bundle(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def wait_for_server(api_url: str, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    base = api_url.rstrip("/")
    candidates = [f"{base}/health", base]
    while time.monotonic() < deadline:
        for url in candidates:
            try:
                response = requests.get(url, timeout=3.0)
                if response.ok:
                    return
            except Exception:
                continue
        time.sleep(2.0)
    raise RuntimeError(f"SPX server at {api_url} did not become healthy within {timeout} seconds")


def resolve_model_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = (BASE_DIR / path).resolve()
    return path


def bootstrap(bundle_path: Path, api_url: str) -> None:
    bundle = load_bundle(bundle_path)
    models = bundle.get("models", [])
    instances = bundle.get("instances", [])
    start_instances = [str(key).strip() for key in bundle.get("start_instances", []) or [] if str(key).strip()]
    if not models:
        print("[bootstrap] No models defined in bundle; nothing to do.")
        return

    wait_for_server(api_url)
    if spx_python is not None:
        client = spx_python.init(address=api_url, product_key=bundle.get("license_key", ""))
        model_payloads: Dict[str, Dict[str, Any]] = {}
        for entry in models:
            payload = register_via_sdk(client, entry)
            if payload and isinstance(payload, dict):
                model_id = entry.get("id")
                if isinstance(model_id, str) and model_id:
                    model_payloads[model_id] = payload
        for entry in instances:
            create_instance_via_sdk(client, entry, model_payloads)
        for instance_key in start_instances:
            start_instance_via_sdk(client, instance_key)
    else:
        register_via_http(api_url, bundle.get("license_key", ""), models)
        if instances:
            print("[bootstrap] Instance creation skipped (spx_python not available).")
        if start_instances:
            print("[bootstrap] Instance start skipped (spx_python not available).")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bootstrap models/instances into SPX server")
    parser.add_argument("--bundle", required=True, help="Path to bundle JSON produced by installer")
    parser.add_argument("--api-url", default=DEFAULT_API, help="SPX server API base URL")
    args = parser.parse_args(argv)

    bootstrap(Path(args.bundle), args.api_url)
    return 0


def register_via_sdk(client, entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    model_id = entry.get("id")
    raw_path = entry.get("path", "")
    model_path = resolve_model_path(raw_path)
    if not model_id or not model_path.exists():
        print(f"  - Skipping invalid entry: {entry}")
        return None
    with model_path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    client["models"][model_id] = payload
    print(f"  - Registered model {model_id} via SDK")
    return payload


def _meta_defaults(payload: Dict[str, Any]) -> tuple[Dict[str, Any], list[str]]:
    meta = payload.get("meta_parameters", {})
    if not isinstance(meta, dict):
        return {}, []
    params: Dict[str, Any] = {}
    missing: list[str] = []
    for name, spec in meta.items():
        if not isinstance(spec, dict):
            continue
        if "default" in spec:
            params[name] = {"cycle": [spec.get("default")]}
        elif spec.get("required") is True:
            missing.append(name)
    return params, missing


def create_instance_via_sdk(
    client,
    entry: Dict[str, Any],
    model_payloads: Dict[str, Dict[str, Any]],
) -> None:
    model_id = entry.get("model_id")
    instance_key = entry.get("instance_key")
    if not model_id or not instance_key:
        return
    payload = model_payloads.get(model_id, {})
    has_meta = isinstance(payload, dict) and bool(payload.get("meta_parameters"))
    if has_meta:
        params, missing = _meta_defaults(payload)
        if missing:
            raise RuntimeError(
                f"Missing defaults for required meta_parameters in {model_id}: {', '.join(missing)}"
            )
        if params:
            client["instances"].generate(
                template=model_id,
                count=1,
                name=instance_key,
                parameters=params,
            )
            print(f"  - Generated instance {instance_key} from {model_id}")
            return
    client["instances"][instance_key] = model_id
    print(f"  - Created instance {instance_key} from {model_id}")


def start_instance_via_sdk(client, instance_key: str) -> None:
    if not instance_key:
        return
    try:
        instance = client["instances"][instance_key]
    except Exception:
        print(f"  - Skipping start for {instance_key} (instance not found)")
        return
    try:
        instance.start()
        print(f"  - Started instance {instance_key}")
    except Exception as exc:
        print(f"  - Failed to start instance {instance_key}: {exc}")


def register_via_http(api_url: str, product_key: str, models: list[Dict[str, Any]]) -> None:
    session = requests.Session()
    if product_key:
        session.headers.update({"X-SPX-PRODUCT-KEY": product_key})
    for entry in models:
        model_id = entry.get("id")
        raw_path = entry.get("path", "")
        model_path = resolve_model_path(raw_path)
        if not model_id or not model_path.exists():
            print(f"  - Skipping invalid entry: {entry}")
            continue
        with model_path.open("r", encoding="utf-8") as handle:
            payload = handle.read()
        resp = session.post(
            f"{api_url.rstrip('/')}/models",
            headers={"Content-Type": "application/x-yaml"},
            params={"model_id": model_id},
            data=payload,
            timeout=10.0,
        )
        resp.raise_for_status()
        print(f"  - Registered model {model_id} via HTTP")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
"""
        path = output_dir / "bootstrap_runner.py"
        path.write_text(runner, encoding="utf-8")

    def _write_runtime_bootstrap(self, output_dir: Path) -> None:
        src = self.repo_root / "installer" / "runtime_bootstrap.py"
        if not src.exists():
            src = Path(__file__).with_name("runtime_bootstrap.py")
        if not src.exists():
            raise FileNotFoundError(f"Missing runtime bootstrap helper: {src}")

        dest = output_dir / "runtime_bootstrap.py"
        shutil.copy2(src, dest)
        mode = os.stat(dest).st_mode
        os.chmod(dest, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    def _write_macos_python_helper(self, output_dir: Path) -> None:
        src = self.repo_root / "installer" / "macos" / "python_runtime.sh"
        if not src.exists():
            src = Path(__file__).parent / "macos" / "python_runtime.sh"
        if not src.exists():
            raise FileNotFoundError(f"Missing macOS Python runtime helper: {src}")

        dest = output_dir / "macos_python_runtime.sh"
        shutil.copy2(src, dest)
        mode = os.stat(dest).st_mode
        os.chmod(dest, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
