# SPDX-License-Identifier: MIT
"""Selection resolution helpers for the installer CLI/wizard."""

from __future__ import annotations

from typing import Any, Dict, List, Sequence, Set, Tuple

from .manifest import ManifestIndex


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
        result.update(
            {
                model_id
                for model_id, manifest in index.models.items()
                if any(proto in manifest.protocols for proto in protocols)
            }
        )

    profile_model_paths = {
        path
        for profile_id in profiles
        for path in index.profiles[profile_id].models
    }
    if profile_model_paths:
        path_to_model = {manifest.path: model_id for model_id, manifest in index.models.items()}
        for profile_path in profile_model_paths:
            model_id = path_to_model.get(profile_path)
            if model_id:
                result.add(model_id)

    return sorted(result)


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

