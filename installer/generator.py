# SPDX-License-Identifier: MIT
"""Generate deployment artifacts (docker-compose, helper scripts, env files)."""

from __future__ import annotations

import os
import stat
import json
import shutil
from pathlib import Path
from typing import Dict, List

import yaml

from .manifest import ManifestIndex, ServiceManifest
from . import paths


SPX_SERVER_SERVICE_NAME = "spx-server"
SPX_SERVER_IMAGE = "simplephysx/spx-server:v1.0.0-rc.12"


class DeploymentGenerator:
    """Create runnable artifacts from wizard selections."""

    def __init__(self, index: ManifestIndex) -> None:
        self.index = index
        self.repo_root = paths.repo_root()

    def generate(self, selection, output_dir: Path) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)

        assets_root = output_dir / "assets"
        assets_root.mkdir(parents=True, exist_ok=True)

        compose_data = self._build_compose(selection.service_ids, assets_root)
        compose_path = output_dir / "docker-compose.generated.yml"
        with compose_path.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(compose_data, handle, sort_keys=False)

        self._write_env(output_dir, selection.license_key)
        self._write_bundle(output_dir, selection)
        start_script = """
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN=${PYTHON_BIN:-python3}
REQUIRED_MODULES=(requests spx_python)
BLE_ADAPTER_PORT=${BLE_ADAPTER_PORT:-8085}
BLE_ADAPTER_PID=""

cleanup_on_failure() {
  local status=$?
  trap - ERR INT TERM
  echo "[spx-start] Encountered an error, cleaning up (exit code ${status})" >&2
  if [ -n "${BLE_ADAPTER_PID:-}" ] && kill -0 "${BLE_ADAPTER_PID}" >/dev/null 2>&1; then
    kill "${BLE_ADAPTER_PID}" >/dev/null 2>&1 || true
  fi
  docker compose -f "$SCRIPT_DIR/docker-compose.generated.yml" --env-file "$SCRIPT_DIR/.env" down --remove-orphans >/dev/null 2>&1 || true
  exit "${status}"
}

trap cleanup_on_failure ERR INT TERM

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "[spx-start] Missing required command: $1" >&2
    exit 1
  fi
}

check_python_modules() {
  local missing=()
  for module in "${REQUIRED_MODULES[@]}"; do
    if ! "$PYTHON_BIN" -c "import ${module}" >/dev/null 2>&1; then
      missing+=("$module")
    fi
  done
  if [ ${#missing[@]} -eq 0 ]; then
    return
  fi
  echo "[spx-start] Missing Python modules: ${missing[*]}"
  echo "            Install them via 'pip install spx-python requests' and rerun."
  exit 1
}

need_cmd docker
need_cmd "$PYTHON_BIN"
check_python_modules

# Optional BLE adapter (NodeJS) support
HAS_BLE=$(
  SCRIPT_DIR="$SCRIPT_DIR" "$PYTHON_BIN" - <<'PY'
import json, pathlib, os
bundle_path = pathlib.Path(os.environ.get("SCRIPT_DIR", ".")) / "bundle.json"
try:
    data = json.loads(bundle_path.read_text(encoding="utf-8"))
    print("yes" if "btvirt_adapter" in data.get("services", []) else "no")
except Exception:
    print("no")
PY
)
if [ "$HAS_BLE" = "yes" ]; then
  if command -v npm >/dev/null 2>&1; then
    if command -v spx-ble-adapter >/dev/null 2>&1; then
      echo "[spx-start] Updating BLE adapter '@simplephysx/spx-ble-adapter' via npm -g"
      npm update -g @simplephysx/spx-ble-adapter
    else
      echo "[spx-start] Installing BLE adapter '@simplephysx/spx-ble-adapter' via npm -g"
      npm install -g @simplephysx/spx-ble-adapter
    fi
    echo "[spx-start] Starting BLE adapter on port ${BLE_ADAPTER_PORT}"
    spx-ble-adapter --port "${BLE_ADAPTER_PORT}" >/dev/null 2>&1 &
    BLE_ADAPTER_PID=$!
  else
    echo "[spx-start] npm not available; skipping BLE adapter start" >&2
  fi
fi

docker compose -f "$SCRIPT_DIR/docker-compose.generated.yml" --env-file "$SCRIPT_DIR/.env" down --remove-orphans >/dev/null 2>&1 || true
docker compose -f "$SCRIPT_DIR/docker-compose.generated.yml" --env-file "$SCRIPT_DIR/.env" up -d
"$PYTHON_BIN" -m installer bootstrap --bundle "$SCRIPT_DIR/bundle.json"
"""
        start_script_ps1 = r"""
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonBin = if ($Env:PYTHON_BIN) { $Env:PYTHON_BIN } elseif (Get-Command python3 -ErrorAction SilentlyContinue) { "python3" } else { "python" }
$RequiredModules = @("requests", "spx_python")
$BleAdapterPort = if ($Env:BLE_ADAPTER_PORT) { $Env:BLE_ADAPTER_PORT } else { 8085 }
$bleProcess = $null

function Need-Command {
    param([string]$Command)
    if (-not (Get-Command $Command -ErrorAction SilentlyContinue)) {
        throw "[spx-start] Missing required command: $Command"
    }
}

function Check-PythonModules {
    $missing = @()
    foreach ($module in $RequiredModules) {
        & $PythonBin -c "import $module" 2>$null
        if ($LASTEXITCODE -ne 0) {
            $missing += $module
        }
    }
    if ($missing.Count -gt 0) {
        Write-Error "[spx-start] Missing Python modules: $($missing -join ', ')"
        Write-Host "            Install them via 'pip install spx-python requests' and rerun."
        throw "Missing Python modules"
    }
}

function Cleanup-OnFailure {
    param([int]$ExitCode = 1)
    if ($bleProcess -and -not $bleProcess.HasExited) {
        try { $bleProcess.Kill() | Out-Null } catch {}
    }
    try {
        docker compose -f (Join-Path $ScriptDir "docker-compose.generated.yml") --env-file (Join-Path $ScriptDir ".env") down --remove-orphans | Out-Null
    } catch {}
    exit $ExitCode
}

try {
    Need-Command "docker"
    Need-Command $PythonBin
    Check-PythonModules

    $bundlePath = Join-Path $ScriptDir "bundle.json"
    $hasBle = $false
    if (Test-Path $bundlePath) {
        try {
            $bundle = Get-Content $bundlePath -Raw | ConvertFrom-Json
            if ($bundle.services -and ($bundle.services -contains "btvirt_adapter")) {
                $hasBle = $true
            }
        } catch {
            $hasBle = $false
        }
    }

    if ($hasBle) {
        if (Get-Command npm -ErrorAction SilentlyContinue) {
            if (Get-Command spx-ble-adapter -ErrorAction SilentlyContinue) {
                Write-Host "[spx-start] Updating BLE adapter '@simplephysx/spx-ble-adapter' via npm -g"
                npm update -g '@simplephysx/spx-ble-adapter' | Out-Null
            } else {
                Write-Host "[spx-start] Installing BLE adapter '@simplephysx/spx-ble-adapter' via npm -g"
                npm install -g '@simplephysx/spx-ble-adapter' | Out-Null
            }
            Write-Host "[spx-start] Starting BLE adapter on port $BleAdapterPort"
            $bleProcess = Start-Process "spx-ble-adapter" -ArgumentList "--port", "$BleAdapterPort" -NoNewWindow -PassThru
        } else {
            Write-Warning "[spx-start] npm not available; skipping BLE adapter start"
        }
    }

    docker compose -f (Join-Path $ScriptDir "docker-compose.generated.yml") --env-file (Join-Path $ScriptDir ".env") down --remove-orphans | Out-Null
    docker compose -f (Join-Path $ScriptDir "docker-compose.generated.yml") --env-file (Join-Path $ScriptDir ".env") up -d
    & $PythonBin -m installer bootstrap --bundle (Join-Path $ScriptDir "bundle.json")
}
catch {
    Write-Error "[spx-start] Encountered an error: $($_.Exception.Message)"
    Cleanup-OnFailure 1
}
"""
        self._write_script(output_dir / "spx-start.sh", start_script.strip() + "\n")
        self._write_ps_script(output_dir / "spx-start.ps1", start_script_ps1.strip() + "\n")
        stop_script = """
pkill -f spx-ble-adapter >/dev/null 2>&1 || true
docker compose -f "$(dirname "$0")/docker-compose.generated.yml" --env-file "$(dirname "$0")/.env" down
"""
        stop_script_ps1 = r"""
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

try {
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -match "spx-ble-adapter" } | ForEach-Object {
        try {
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        } catch {}
    }
} catch {}

docker compose -f (Join-Path $ScriptDir "docker-compose.generated.yml") --env-file (Join-Path $ScriptDir ".env") down
"""
        self._write_script(output_dir / "spx-stop.sh", stop_script.strip() + "\n")
        self._write_ps_script(output_dir / "spx-stop.ps1", stop_script_ps1.strip() + "\n")

    # Internal helpers -------------------------------------------------------
    def _build_compose(self, service_ids: List[str], assets_root: Path) -> Dict[str, Dict]:
        services: Dict[str, Dict] = {}
        builtin_ports: List[str] = []
        docker_services: Dict[str, ServiceManifest] = {}
        native_services: List[ServiceManifest] = []

        for service_id in service_ids:
            manifest = self.index.services.get(service_id)
            if not manifest or not manifest.deployment:
                continue
            runtime = manifest.deployment.runtime
            if runtime == "builtin":
                builtin_ports.extend(self._format_ports(manifest))
            elif runtime == "docker":
                docker_services[service_id] = manifest
            else:
                native_services.append(manifest)

        services[SPX_SERVER_SERVICE_NAME] = self._build_spx_server_service(builtin_ports, assets_root)

        for service_id, manifest in docker_services.items():
            services[service_id] = self._build_docker_service(manifest, assets_root)

        compose = {
            "services": services,
        }
        if native_services:
            compose.setdefault("x-native-services", [])  # hint for future steps
            compose["x-native-services"] = [svc.id for svc in native_services]
        return compose

    def _build_spx_server_service(self, extra_ports: List[str], assets_root: Path) -> Dict:
        ports = ["8000:8000"]
        for port in extra_ports:
            if port not in ports:
                ports.append(port)

        volumes = [self._process_volume("./extensions:/app/extensions", assets_root)]
        service = {
            "image": SPX_SERVER_IMAGE,
            "container_name": "spx-server",
            "ports": ports,
            "environment": {
                "SPX_PRODUCT_KEY": "${SPX_PRODUCT_KEY}",
            },
            "healthcheck": {
                "test": ["CMD-SHELL", "curl -f http://localhost:8000 || exit 1"],
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

    def _build_docker_service(self, manifest: ServiceManifest, assets_root: Path) -> Dict:
        deployment = manifest.deployment
        assert deployment is not None
        service = {
            "image": deployment.image,
            "container_name": deployment.container_name or manifest.id,
        }
        ports = self._format_ports(manifest)
        if ports:
            service["ports"] = ports
        if deployment.volumes:
            service["volumes"] = [self._process_volume(entry, assets_root) for entry in deployment.volumes]
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

    def _format_ports(self, manifest: ServiceManifest) -> List[str]:
        entries = []
        for port in manifest.ports:
            entry = f"{port.host}:{port.container}"
            if port.transport.lower() == "udp":
                entry = f"{port.host}:{port.container}/udp"
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
        prefix_removed = False
        if host.startswith("./"):
            clean = host[2:]
        else:
            clean = host

        relative = None
        if clean.startswith("library/assets/"):
            relative = clean[len("library/assets/"):]
        elif clean.startswith("docker/"):
            relative = clean[len("docker/"):]

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
            shutil.copy2(src, dest)

        return f"./assets/{relative}"

    def _write_env(self, output_dir: Path, product_key: str) -> None:
        env_path = output_dir / ".env"
        value = product_key or "REPLACE_ME"
        env_path.write_text(f"SPX_PRODUCT_KEY={value}\n", encoding="utf-8")

    def _write_script(self, path: Path, command: str) -> None:
        script = "#!/usr/bin/env bash\nset -euo pipefail\n" + command
        path.write_text(script, encoding="utf-8")
        mode = os.stat(path).st_mode
        os.chmod(path, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    def _write_ps_script(self, path: Path, command: str) -> None:
        path.write_text(command, encoding="utf-8")

    def _write_bundle(self, output_dir: Path, selection) -> None:
        bundle = {
            "packages": selection.packages,
            "protocols": selection.protocols,
            "license_key": selection.license_key,
            "models": [
                {
                    "id": model_id,
                    "path": str(self.index.models[model_id].path),
                }
                for model_id in selection.model_ids
            ],
            "instances": self._collect_instances(selection),
            "services": selection.service_ids,
        }
        bundle_path = output_dir / "bundle.json"
        bundle_path.write_text(json.dumps(bundle, indent=2), encoding="utf-8")

    def _collect_instances(self, selection) -> list[dict[str, str]]:
        instances: list[dict[str, str]] = []
        for pkg in selection.packages:
            manifest = self.index.industries.get(pkg)
            if not manifest:
                continue
            for entry in manifest.default_instances:
                model_id = entry.get("model")
                instance_key = entry.get("instance")
                if model_id and instance_key:
                    instances.append({"model_id": model_id, "instance_key": instance_key})
        return instances
