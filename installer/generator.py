# SPDX-License-Identifier: MIT
"""Generate deployment artifacts (docker-compose, helper scripts, env files)."""

from __future__ import annotations

import os
import stat
import json
import shutil
from pathlib import Path
from typing import Dict, List, Set

import yaml

from .manifest import ManifestIndex, ServiceManifest
from . import paths


SPX_SERVER_SERVICE_NAME = "spx-server"
SPX_SERVER_IMAGE = "simplephysx/spx-server:v1.0.0-rc.54"
SPX_SERVER_IMAGE = "simplephysx/spx-server:v1.0.0-rc.54"
# SPX_SERVER_IMAGE = "spx-server:trial"
SPX_UI_SERVICE_NAME = "spx-ui"
SPX_UI_IMAGE = "simplephysx/spx-ui:v1.0.0-rc.55"


class DeploymentGenerator:
    """Create runnable artifacts from wizard selections."""

    def __init__(self, index: ManifestIndex) -> None:
        self.index = index
        self.repo_root = paths.repo_root()

    def generate(self, selection, output_dir: Path) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)

        assets_root = output_dir / "assets"
        assets_root.mkdir(parents=True, exist_ok=True)

        # Bundle local extensions so generated artifacts remain self-contained.
        extensions_src = self.repo_root / "extensions"
        if extensions_src.exists():
            shutil.copytree(extensions_src, output_dir / "extensions", dirs_exist_ok=True)

        compose_data = self._build_compose(selection.service_ids, assets_root, selection.install_spx_ui)
        compose_path = output_dir / "docker-compose.generated.yml"
        with compose_path.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(compose_data, handle, sort_keys=False)

        self._write_env(output_dir, selection.license_key)
        self._write_bundle(output_dir, selection)
        bootstrap_cmd_sh = '"$PYTHON_BIN" "$SCRIPT_DIR/bootstrap_runner.py" --bundle "$SCRIPT_DIR/bundle.json"\n'
        bootstrap_cmd_ps = '    & $PythonBin (Join-Path $ScriptDir "bootstrap_runner.py") --bundle (Join-Path $ScriptDir "bundle.json")\n'
        if not selection.install_examples:
            bootstrap_cmd_sh = 'echo "[spx-start] Skipping example bootstrap per installer selection."\n'
            bootstrap_cmd_ps = '    Write-Host "[spx-start] Skipping example bootstrap per installer selection."\n'

        start_script = """
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -z "${PYTHON_BIN:-}" ]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN=python3
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN=python
  else
    echo "[spx-start] Missing required command: python3 or python" >&2
    exit 1
  fi
fi
REQUIRED_MODULES=(requests:requests spx_python:spx-python yaml:pyyaml)
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
  local packages=()
  for entry in "${REQUIRED_MODULES[@]}"; do
    local module="${entry%%:*}"
    local package="${entry##*:}"
    if ! "$PYTHON_BIN" -c "import ${module}" >/dev/null 2>&1; then
      missing+=("$module")
      packages+=("$package")
    fi
  done
  if [ ${#missing[@]} -eq 0 ]; then
    return
  fi
  echo "[spx-start] Missing Python modules: ${missing[*]}. Installing via pip..."
  "$PYTHON_BIN" -m pip install --user "${packages[@]}"
  for module in "${missing[@]}"; do
    if ! "$PYTHON_BIN" -c "import ${module}" >/dev/null 2>&1; then
      echo "[spx-start] Unable to import module '${module}' even after pip install." >&2
      exit 1
    fi
  done
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
echo "[spx-start] Active container ports:"
docker compose -f "$SCRIPT_DIR/docker-compose.generated.yml" --env-file "$SCRIPT_DIR/.env" ps
__BOOTSTRAP_CMD_SH__
echo ""
echo "[spx-start] SPX started successfully."
echo "[spx-start] UI: http://localhost:3000 (if enabled), API: http://localhost:8000"
echo "[spx-start] You can now open the available services and start playing with SPX :)"
"""
        start_script = start_script.replace("__BOOTSTRAP_CMD_SH__", bootstrap_cmd_sh).strip("\n")
        start_script_ps1 = r"""
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Env:COMPOSE_PROGRESS) { $Env:COMPOSE_PROGRESS = "plain" }
if (-not $Env:BUILDKIT_PROGRESS) { $Env:BUILDKIT_PROGRESS = "plain" }

function Test-PythonCommand {
    param([string]$Command)
    try {
        & $Command -c "import sys" 2>$null | Out-Null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

function Resolve-Python {
    if ($Env:PYTHON_BIN) {
        if (Test-PythonCommand $Env:PYTHON_BIN) {
            return $Env:PYTHON_BIN
        }
        throw "[spx-start] PYTHON_BIN is set to '$Env:PYTHON_BIN' but is not a working Python interpreter."
    }

    foreach ($candidate in @("python3", "python")) {
        if (Get-Command $candidate -ErrorAction SilentlyContinue) {
            if (Test-PythonCommand $candidate) {
                return $candidate
            }
        }
    }

    throw "[spx-start] Missing required command: python (3.x). Install Python 3 or set PYTHON_BIN."
}

$PythonBin = Resolve-Python
$RequiredModules = @(
    @{ Module = "requests"; Package = "requests" },
    @{ Module = "spx_python"; Package = "spx-python" },
    @{ Module = "yaml"; Package = "pyyaml" }
)
$BleAdapterPort = if ($Env:BLE_ADAPTER_PORT) { $Env:BLE_ADAPTER_PORT } else { 8085 }
$bleProcess = $null

function Need-Command {
    param([string]$Command)
    if (-not (Get-Command $Command -ErrorAction SilentlyContinue)) {
        throw "[spx-start] Missing required command: $Command"
    }
}

function Check-PythonModules {
    function Test-PythonModule {
        param([string]$Module)
        $checkCmd = "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('$Module') else 1)"
        try {
            & $PythonBin -c $checkCmd 2>$null | Out-Null
        } catch {
            return $false
        }
        return ($LASTEXITCODE -eq 0)
    }

    $missing = @()
    foreach ($entry in $RequiredModules) {
        if (-not (Test-PythonModule $entry.Module)) {
            $missing += $entry
        }
    }
    if ($missing.Count -eq 0) {
        return
    }
    $moduleNames = $missing | ForEach-Object { $_.Module }
    $packages = $missing | ForEach-Object { $_.Package }
    Write-Host "[spx-start] Missing Python modules: $($moduleNames -join ', '). Installing via pip..."
    & $PythonBin -m pip install --user @($packages)
    if ($LASTEXITCODE -ne 0) {
        throw "[spx-start] pip install failed"
    }
    foreach ($entry in $missing) {
        if (-not (Test-PythonModule $entry.Module)) {
            throw "[spx-start] Unable to import module '$($entry.Module)' even after pip install."
        }
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
    docker compose -f (Join-Path $ScriptDir "docker-compose.generated.yml") --env-file (Join-Path $ScriptDir ".env") up -d | Out-Null
    Write-Host "[spx-start] Active container ports:"
    docker compose -f (Join-Path $ScriptDir "docker-compose.generated.yml") --env-file (Join-Path $ScriptDir ".env") ps
__BOOTSTRAP_CMD_PS__
    Write-Host ""
    Write-Host "[spx-start] SPX started successfully."
    Write-Host "[spx-start] UI: http://localhost:3000 (if enabled), API: http://localhost:8000"
    Write-Host "[spx-start] You can now open the available services and start playing with SPX :)"
}
catch {
    Write-Error "[spx-start] Encountered an error: $($_.Exception.Message)"
    Cleanup-OnFailure 1
}
"""
        start_script_ps1 = start_script_ps1.replace("__BOOTSTRAP_CMD_PS__", bootstrap_cmd_ps)
        self._write_script(output_dir / "spx-start.sh", start_script.strip() + "\n")
        self._write_ps_script(output_dir / "spx-start.ps1", start_script_ps1.strip() + "\n")
        start_command = """#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

bash "./spx-start.sh" "$@"
EXIT_CODE=$?

echo ""
echo "Exit code: $EXIT_CODE"
read -r -p "Press Enter to close..." _
exit $EXIT_CODE
"""
        start_bat = r"""@echo off
setlocal

cd /d "%~dp0"

powershell -ExecutionPolicy Bypass -NoProfile -File "%~dp0spx-start.ps1" %*
set "EXITCODE=%ERRORLEVEL%"
echo Exit code: %EXITCODE%
pause
exit /b %EXITCODE%
"""
        self._write_text_script(output_dir / "spx-start.command", start_command.strip() + "\n", executable=True)
        self._write_text_script(output_dir / "spx-start.bat", start_bat.strip() + "\n")
        self._write_bootstrap_runner(output_dir)
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
        stop_command = """#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

bash "./spx-stop.sh" "$@"
EXIT_CODE=$?

echo ""
echo "Exit code: $EXIT_CODE"
read -r -p "Press Enter to close..." _
exit $EXIT_CODE
"""
        stop_bat = r"""@echo off
setlocal

cd /d "%~dp0"

powershell -ExecutionPolicy Bypass -NoProfile -File "%~dp0spx-stop.ps1" %*
set "EXITCODE=%ERRORLEVEL%"
echo Exit code: %EXITCODE%
pause
exit /b %EXITCODE%
"""
        self._write_text_script(output_dir / "spx-stop.command", stop_command.strip() + "\n", executable=True)
        self._write_text_script(output_dir / "spx-stop.bat", stop_bat.strip() + "\n")

    # Internal helpers -------------------------------------------------------
    def _build_compose(self, service_ids: List[str], assets_root: Path, include_ui: bool) -> Dict[str, Dict]:
        services: Dict[str, Dict] = {}
        builtin_ports: List[str] = []
        docker_services: Dict[str, ServiceManifest] = {}
        native_services: List[ServiceManifest] = []
        modbus_enabled = False

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
            if service_id == "modbus_tcp_gateway":
                modbus_enabled = True

        if modbus_enabled:
            # Expose an extended Modbus TCP range for multi-instance demos.
            builtin_ports.extend([f"{port}:{port}" for port in range(5020, 5121)])

        services[SPX_SERVER_SERVICE_NAME] = self._build_spx_server_service(builtin_ports, assets_root)
        if include_ui:
            services[SPX_UI_SERVICE_NAME] = self._build_spx_ui_service()

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
            # Ensure host.docker.internal resolves on Linux (Docker Engine) for models
            # that reference host-mapped service ports (e.g., MQTT, LwM2M, BLE bridge).
            "extra_hosts": ["host.docker.internal:host-gateway"],
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

    def _build_spx_ui_service(self) -> Dict:
        return {
            "image": SPX_UI_IMAGE,
            "container_name": "spx-ui-server",
            "depends_on": {
                SPX_SERVER_SERVICE_NAME: {
                    "condition": "service_healthy",
                }
            },
            "ports": ["3000:3000"],
            "environment": {
                "SPX_PRODUCT_KEY": "${SPX_PRODUCT_KEY}",
            },
            "command": [
                "--product-key",
                "${SPX_PRODUCT_KEY}",
            ],
        }

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
            transport = port.transport.lower()
            if transport == "udp":
                if manifest.id == "bacnet_gateway":
                    bind = "${BACNET_BIND_ADDR:-127.0.0.1}"
                    entry = f"{bind}:{port.host}:{port.container}/udp"
                else:
                    entry = f"{port.host}:{port.container}/udp"
            else:
                entry = f"{port.host}:{port.container}"
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

    def _write_text_script(self, path: Path, command: str, *, executable: bool = False) -> None:
        path.write_text(command, encoding="utf-8")
        if executable:
            mode = os.stat(path).st_mode
            os.chmod(path, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    def _write_bundle(self, output_dir: Path, selection) -> None:
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
            "license_key": selection.license_key,
            "models": model_entries,
            "instances": self._collect_instances(selection),
            "start_instances": list(selection.start_instances),
            "services": selection.service_ids,
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

    def _write_bootstrap_runner(self, output_dir: Path) -> None:
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
        model_payloads: Dict[str, Dict[str, Any]] = {}
        for entry in models:
            payload = register_via_sdk(client, entry)
            if payload and isinstance(payload, dict):
                model_id = entry.get("id")
                if isinstance(model_id, str) and model_id:
                    model_payloads[model_id] = payload
            payload = register_via_sdk(client, entry)
            if payload and isinstance(payload, dict):
                model_id = entry.get("id")
                if isinstance(model_id, str) and model_id:
                    model_payloads[model_id] = payload
        for entry in instances:
            create_instance_via_sdk(client, entry, model_payloads)
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
def register_via_sdk(client, entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    model_id = entry.get("id")
    raw_path = entry.get("path", "")
    model_path = resolve_model_path(raw_path)
    if not model_id or not model_path.exists():
        print(f"  - Skipping invalid entry: {entry}")
        return None
        return None
    with model_path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    client["models"][model_id] = payload
    print(f"  - Registered model {model_id} via SDK")
    return payload
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
