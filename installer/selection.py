# SPDX-License-Identifier: MIT
"""Selection resolution helpers for the installer CLI/wizard."""

from __future__ import annotations

import platform
from dataclasses import dataclass
from typing import Any, Dict, List, Sequence, Set, Tuple

from .manifest import ManifestIndex

PLATFORM_LABELS = {
    "linux": "Linux",
    "macos": "macOS",
    "windows": "Windows",
}


@dataclass(frozen=True)
class PlatformCompatibilityAdjustment:
    model_ids: List[str]
    service_ids: List[str]
    instances: List[Dict[str, Any]]
    start_instances: List[str]
    warnings: List[str]


def current_platform_name(platform_name: str | None = None) -> str:
    """Normalize the current host platform into catalog-friendly labels."""

    raw = (platform_name or platform.system() or "").strip().lower()
    if raw.startswith("win"):
        return "windows"
    if raw in {"darwin", "mac", "macos", "osx"}:
        return "macos"
    if raw.startswith("linux"):
        return "linux"
    return raw or "unknown"


def _service_supported_on_platform(
    service_id: str, index: ManifestIndex, platform_name: str
) -> bool:
    manifest = index.services.get(service_id)
    if manifest is None or manifest.deployment is None:
        return True

    deployment = manifest.deployment
    if deployment.runtime != "native":
        return True

    commands = {str(key).lower(): value for key, value in deployment.commands.items()}
    if commands.get(platform_name):
        return True

    instructions = {
        str(key).lower(): str(value).strip().lower()
        for key, value in deployment.instructions.items()
    }
    instruction = instructions.get(platform_name, "")
    if "not supported" in instruction:
        return False
    return True


def apply_platform_compatibility(
    *,
    model_ids: Sequence[str],
    service_ids: Sequence[str],
    instances: Sequence[Dict[str, Any]],
    start_instances: Sequence[str],
    index: ManifestIndex,
    platform_name: str | None = None,
) -> PlatformCompatibilityAdjustment:
    """Prune services/models/instances that are not supported on the current platform."""

    normalized_platform = current_platform_name(platform_name)
    unsupported_service_ids = [
        service_id
        for service_id in service_ids
        if not _service_supported_on_platform(service_id, index, normalized_platform)
    ]
    if not unsupported_service_ids:
        return PlatformCompatibilityAdjustment(
            model_ids=list(model_ids),
            service_ids=list(service_ids),
            instances=[dict(entry) for entry in instances],
            start_instances=list(start_instances),
            warnings=[],
        )

    removed_model_ids: Set[str] = set()
    warnings: List[str] = []

    for service_id in unsupported_service_ids:
        service_manifest = index.services.get(service_id)
        service_name = (
            service_manifest.name if service_manifest is not None else service_id
        )
        service_models = [
            model_id
            for model_id in model_ids
            if service_id
            in (
                index.models.get(model_id).services
                if index.models.get(model_id)
                else []
            )
        ]
        removed_model_ids.update(service_models)
        removed_instance_keys = [
            str(entry.get("instance_key"))
            for entry in instances
            if entry.get("model_id") in service_models and entry.get("instance_key")
        ]

        service_label = service_name
        if service_manifest is not None and service_manifest.protocol:
            protocol_label = (
                "BLE/GATT"
                if service_manifest.protocol.lower() == "ble"
                else service_manifest.protocol.upper()
            )
            service_label = f"{service_name} ({protocol_label}, {service_id})"
        else:
            service_label = f"{service_name} ({service_id})"

        warning = (
            f"{PLATFORM_LABELS.get(normalized_platform, normalized_platform.title())} does not "
            f"support {service_label}; skipping this service"
        )
        if service_models:
            model_names = [
                index.models[model_id].name
                for model_id in service_models
                if model_id in index.models
            ]
            warning += f" and removing dependent models: {', '.join(model_names)}"
        if removed_instance_keys:
            warning += f"; removed instances: {', '.join(removed_instance_keys)}"
        warnings.append(warning + ".")

    filtered_model_ids = [
        model_id for model_id in model_ids if model_id not in removed_model_ids
    ]
    filtered_service_ids = [
        service_id
        for service_id in service_ids
        if service_id not in unsupported_service_ids
    ]
    filtered_instances = [
        dict(entry)
        for entry in instances
        if entry.get("model_id") not in removed_model_ids
    ]
    removed_instance_keys = {
        str(entry.get("instance_key"))
        for entry in instances
        if entry.get("model_id") in removed_model_ids and entry.get("instance_key")
    }
    filtered_start_instances = [
        instance_key
        for instance_key in start_instances
        if instance_key not in removed_instance_keys
    ]

    return PlatformCompatibilityAdjustment(
        model_ids=filtered_model_ids,
        service_ids=filtered_service_ids,
        instances=filtered_instances,
        start_instances=filtered_start_instances,
        warnings=warnings,
    )


def resolve_model_ids(
    packages: Sequence[str],
    profiles: Sequence[str],
    protocols: Sequence[str],
    index: ManifestIndex,
) -> List[str]:
    """Resolve model IDs from package/profile/protocol filters."""

    result: Set[str] = {
        model_id
        for model_id, manifest in index.models.items()
        if any(pkg in manifest.packages for pkg in packages)
    }
    if protocols:
        result.update(resolve_protocol_model_ids(protocols, index))

    profile_model_paths = {
        path for profile_id in profiles for path in index.profiles[profile_id].models
    }
    if profile_model_paths:
        path_to_model = {
            manifest.path: model_id for model_id, manifest in index.models.items()
        }
        for profile_path in profile_model_paths:
            model_id = path_to_model.get(profile_path)
            if model_id:
                result.add(model_id)

    return sorted(result)


def resolve_protocol_model_ids(
    protocols: Sequence[str],
    index: ManifestIndex,
) -> List[str]:
    """Resolve every catalog model compatible with at least one protocol."""

    selected_protocols = set(protocols)
    if not selected_protocols:
        return []
    return sorted(
        model_id
        for model_id, manifest in index.models.items()
        if selected_protocols.intersection(manifest.protocols)
    )


def resolve_protocol_service_ids(
    protocols: Sequence[str],
    index: ManifestIndex,
) -> List[str]:
    """Resolve local services whose protocol is explicitly selected."""

    selected_protocols = set(protocols)
    if not selected_protocols:
        return []
    return sorted(
        service_id
        for service_id, service in index.services.items()
        if service.protocol in selected_protocols
    )


def resolve_service_ids(
    model_ids: Sequence[str],
    packages: Sequence[str],
    profiles: Sequence[str],
    index: ManifestIndex,
) -> List[str]:
    """Resolve service IDs required by the selected models + pack/profile services."""

    services: Set[str] = set()

    for model_id in model_ids:
        manifest = index.models.get(model_id)
        if manifest is None:
            continue
        services.update(manifest.services)

    for pkg in packages:
        industry = index.industries.get(pkg)
        if industry is None:
            continue
        services.update(industry.services)

    for profile_id in profiles:
        profile = index.profiles.get(profile_id)
        if profile is None:
            continue
        services.update(profile.services)

    return sorted(services)


def resolve_default_instances(
    packages: Sequence[str],
    index: ManifestIndex,
) -> List[Dict[str, Any]]:
    """Resolve default instances declared by the selected packages."""

    instances: List[Dict[str, Any]] = []
    seen: Set[Tuple[str, str]] = set()

    for pkg in packages:
        manifest = index.industries.get(pkg)
        if manifest is None:
            continue
        for entry in manifest.default_instances:
            if not isinstance(entry, dict):
                continue
            model_id = entry.get("model")
            instance_key = entry.get("instance")
            if not model_id or not instance_key:
                continue
            key = (str(model_id), str(instance_key))
            if key in seen:
                continue
            seen.add(key)
            instances.append({"model_id": key[0], "instance_key": key[1]})

    return instances


def resolve_start_instances(
    packages: Sequence[str],
    index: ManifestIndex,
) -> List[str]:
    """Resolve instance keys that should be started after creation."""
    start_instances: List[str] = []
    seen: Set[str] = set()

    for pkg in packages:
        manifest = index.industries.get(pkg)
        if manifest is None:
            continue
        default_keys = {
            entry.get("instance")
            for entry in manifest.default_instances
            if isinstance(entry, dict) and entry.get("instance")
        }
        for entry in manifest.start_instances:
            key = str(entry).strip()
            if not key:
                continue
            if default_keys and key not in default_keys:
                continue
            if key in seen:
                continue
            seen.add(key)
            start_instances.append(key)

    return start_instances
