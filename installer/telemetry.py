# SPDX-License-Identifier: MIT
"""Build a minimal, privacy-filtered telemetry manifest for generated stacks."""

from __future__ import annotations

import json
import platform
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TELEMETRY_ENVIRONMENTS = frozenset({"production", "staging"})
TELEMETRY_ENVIRONMENT_FILE = "telemetry_environment.txt"


def resolve_telemetry_environment(installer_root: Path) -> str:
    """Read the allow-listed endpoint environment baked into this installer."""
    try:
        value = (
            (installer_root / TELEMETRY_ENVIRONMENT_FILE)
            .read_text(encoding="utf-8")
            .strip()
        )
    except OSError:
        return "staging"
    return value if value in TELEMETRY_ENVIRONMENTS else "staging"


def _installer_version(repo_root: Path) -> str:
    pyproject = repo_root / "pyproject.toml"
    try:
        content = pyproject.read_text(encoding="utf-8")
    except OSError:
        return "dev"
    match = re.search(r'^\s*version\s*=\s*"([^"]+)"', content, flags=re.MULTILINE)
    return match.group(1).strip() if match else "dev"


def _runtime_os_family() -> str | None:
    return {"windows": "windows", "darwin": "macos", "linux": "linux"}.get(
        platform.system().lower()
    )


def _runtime_architecture() -> str | None:
    machine = platform.machine().lower()
    if machine in {"x86_64", "amd64", "x64"}:
        return "x64"
    if machine in {"aarch64", "arm64"}:
        return "arm64"
    if machine in {"i386", "i486", "i586", "i686", "x86"}:
        return "x86"
    return None


def _unique_valid_ids(values: list[str], pattern: re.Pattern[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        normalized = str(value).lower()
        if pattern.fullmatch(normalized) and normalized not in result:
            result.append(normalized)
    return result


_SELECTION_ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_SERVICE_ID = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")


def build_telemetry_manifest(
    selection: Any,
    *,
    installation_id: str,
    repo_root: Path,
) -> dict[str, Any]:
    """Return the exact configuration event fields supported by spx-www."""
    canonical_installation_id = str(uuid.UUID(hex=installation_id))
    selected_models = list(getattr(selection, "model_ids", []) or [])
    selected_instances = list(getattr(selection, "instances", []) or [])
    started_instances = list(getattr(selection, "start_instances", []) or [])

    selected_packages = _unique_valid_ids(
        list(getattr(selection, "packages", []) or []), _SELECTION_ID
    )
    selected_profiles = _unique_valid_ids(
        list(getattr(selection, "profiles", []) or []), _SELECTION_ID
    )
    selected_protocols = _unique_valid_ids(
        list(getattr(selection, "protocols", []) or []), _SELECTION_ID
    )
    services = _unique_valid_ids(
        list(getattr(selection, "service_ids", []) or []), _SERVICE_ID
    )

    metadata: dict[str, Any] = {
        "services": services,
        "selection": {
            "packages": selected_packages,
            "profiles": selected_profiles,
            "protocols": selected_protocols,
            "install_examples": bool(getattr(selection, "install_examples", False)),
            "install_spx_ui": bool(getattr(selection, "install_spx_ui", False)),
            "offline_bundle": bool(getattr(selection, "offline_bundle", False)),
            "model_count": len(selected_models),
            "planned_instance_count": len(selected_instances),
            "auto_start_instance_count": len(started_instances),
        },
        "installer_version": _installer_version(repo_root),
    }
    os_family = _runtime_os_family()
    architecture = _runtime_architecture()
    if os_family:
        metadata["os_family"] = os_family
    if architecture:
        metadata["architecture"] = architecture

    occurred_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    return {
        "schema_version": 1,
        "installation_id": canonical_installation_id,
        "configuration_event": {
            "schema_version": 1,
            "event_id": str(uuid.uuid4()),
            "event_type": "installation_configured",
            "installation_id": canonical_installation_id,
            "occurred_at": occurred_at.replace("+00:00", "Z"),
            "metadata": metadata,
        },
    }


def write_telemetry_manifest(
    output_dir: Path,
    selection: Any,
    *,
    installation_id: str,
    repo_root: Path,
) -> Path:
    manifest = build_telemetry_manifest(
        selection,
        installation_id=installation_id,
        repo_root=repo_root,
    )
    manifest_path = output_dir / "telemetry.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest_path
