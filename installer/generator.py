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
SPX_SERVER_IMAGE = "simplephysx/spx-server:v1.0.0-rc.11"


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

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "[start-spx] Missing required command: $1" >&2
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
  echo "[start-spx] Missing Python modules: ${missing[*]}"
  echo "            Install them via 'pip install spx-python requests' and rerun."
  exit 1
}

need_cmd docker
need_cmd "$PYTHON_BIN"
check_python_modules

docker compose -f "$SCRIPT_DIR/docker-compose.generated.yml" --env-file "$SCRIPT_DIR/.env" up -d
"$PYTHON_BIN" -m installer bootstrap --bundle "$SCRIPT_DIR/bundle.json"
"""
        self._write_script(output_dir / "start-spx.sh", start_script.strip() + "\n")
        self._write_script(
            output_dir / "stop-spx.sh",
            'docker compose -f "$(dirname "$0")/docker-compose.generated.yml" --env-file "$(dirname "$0")/.env" down\n',
        )

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
            "container_name": "spx-server-examples",
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
