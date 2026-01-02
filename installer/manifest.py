# SPDX-License-Identifier: MIT
"""Manifest loader utilities used by the installer wizard."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

import yaml

from . import paths


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ServicePort:
    transport: str
    host: int
    container: int
    purpose: str = ""


@dataclass(frozen=True)
class ServiceDeployment:
    runtime: str
    provider: Optional[str] = None
    image: Optional[str] = None
    container_name: Optional[str] = None
    hostname: Optional[str] = None
    entrypoint: Optional[List[str]] = None
    command: Optional[List[str]] = None
    volumes: List[str] = field(default_factory=list)
    environment: Dict[str, Any] = field(default_factory=dict)
    restart: Optional[str] = None
    depends_on: List[str] = field(default_factory=list)
    instructions: Dict[str, str] = field(default_factory=dict)
    commands: Dict[str, List[str]] = field(default_factory=dict)
    notes: Optional[str] = None


@dataclass(frozen=True)
class ServiceManifest:
    id: str
    name: str
    protocol: str
    description: str
    ports: List[ServicePort]
    deployment: Optional[ServiceDeployment]


@dataclass(frozen=True)
class ModelManifest:
    id: str
    name: str
    path: Path
    domain: str
    protocols: List[str]
    services: List[str]
    packages: List[str]
    profiles: List[str]


@dataclass(frozen=True)
class DomainManifest:
    id: str
    name: str
    description: str
    path: Path


@dataclass(frozen=True)
class IndustryManifest:
    id: str
    name: str
    description: str
    protocols: List[str]
    services: List[str]
    profiles: List[str]
    path: Path
    default_instances: List[Dict[str, str]] = field(default_factory=list)
    start_instances: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class ProfileManifest:
    id: str
    pack_id: str
    name: str
    description: str
    models: List[Path]
    services: List[str]
    path: Path


@dataclass(frozen=True)
class ManifestIndex:
    services: Dict[str, ServiceManifest]
    models: Dict[str, ModelManifest]
    domains: Dict[str, DomainManifest]
    industries: Dict[str, IndustryManifest]
    profiles: Dict[str, ProfileManifest]


# ---------------------------------------------------------------------------
# Loader implementation
# ---------------------------------------------------------------------------
class ManifestLoader:
    """Loader responsible for parsing all manifest files."""

    def __init__(
        self,
        catalog_dir: Optional[Path] = None,
        profiles_dir: Optional[Path] = None,
    ) -> None:
        self.catalog_dir = Path(catalog_dir) if catalog_dir else paths.catalog_dir()
        self.profiles_dir = Path(profiles_dir) if profiles_dir else paths.profiles_dir()

    # Public API -------------------------------------------------------------
    def load(self) -> ManifestIndex:
        services = self._load_services(self.catalog_dir / "services.yaml")
        models = self._load_models(self.catalog_dir / "models.yaml")
        domains = self._load_domains(self.catalog_dir / "domains.yaml")
        industries = self._load_industries(self.catalog_dir / "industries.yaml")
        profiles = self._load_profiles(self.profiles_dir)

        return ManifestIndex(
            services=services,
            models=models,
            domains=domains,
            industries=industries,
            profiles=profiles,
        )

    # Helpers ----------------------------------------------------------------
    def _load_yaml(self, path: Path) -> Mapping[str, Any]:
        if not path.exists():
            raise FileNotFoundError(f"Manifest file not found: {path}")
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        if not isinstance(data, Mapping):
            raise ValueError(f"Manifest {path} must contain a mapping at the top level.")
        return data

    def _load_services(self, path: Path) -> Dict[str, ServiceManifest]:
        data = self._load_yaml(path).get("services", [])
        services: Dict[str, ServiceManifest] = {}
        for entry in data:
            entry = entry or {}
            service_id = entry.get("id")
            if not service_id:
                continue
            ports = [
                ServicePort(
                    transport=port.get("transport", "tcp"),
                    host=int(port.get("host", 0)),
                    container=int(port.get("container", port.get("host", 0))),
                    purpose=port.get("purpose", ""),
                )
                for port in entry.get("ports", [])
            ]
            deployment = None
            if "deployment" in entry:
                dep = entry["deployment"] or {}
                deployment = ServiceDeployment(
                    runtime=dep.get("runtime", "docker"),
                    provider=dep.get("provider"),
                    image=dep.get("image"),
                    container_name=dep.get("container_name"),
                    hostname=dep.get("hostname"),
                    entrypoint=dep.get("entrypoint"),
                    command=dep.get("command"),
                    volumes=list(dep.get("volumes", []) or []),
                    environment=dict(dep.get("environment", {}) or {}),
                    restart=dep.get("restart"),
                    depends_on=list(dep.get("depends_on", []) or []),
                    instructions=dict(dep.get("instructions", {}) or {}),
                    commands=dict(dep.get("commands", {}) or {}),
                    notes=dep.get("notes"),
                )
            services[service_id] = ServiceManifest(
                id=service_id,
                name=entry.get("name", service_id),
                protocol=entry.get("protocol", ""),
                description=entry.get("description", ""),
                ports=ports,
                deployment=deployment,
            )
        return services

    def _load_models(self, path: Path) -> Dict[str, ModelManifest]:
        data = self._load_yaml(path).get("models", [])
        models: Dict[str, ModelManifest] = {}
        for entry in data:
            entry = entry or {}
            model_id = entry.get("id")
            if not model_id:
                continue
            services = [
                srv["id"] if isinstance(srv, Mapping) else str(srv)
                for srv in entry.get("services", [])
            ]
            models[model_id] = ModelManifest(
                id=model_id,
                name=entry.get("name", model_id),
                path=Path(entry.get("path", "")),
                domain=entry.get("domain", ""),
                protocols=list(entry.get("protocols", []) or []),
                services=services,
                packages=list(entry.get("packages", []) or []),
                profiles=list(entry.get("profiles", []) or []),
            )
        return models

    def _load_domains(self, path: Path) -> Dict[str, DomainManifest]:
        data = self._load_yaml(path).get("domains", [])
        domains: Dict[str, DomainManifest] = {}
        for entry in data:
            entry = entry or {}
            domain_id = entry.get("id")
            if not domain_id:
                continue
            domains[domain_id] = DomainManifest(
                id=domain_id,
                name=entry.get("name", domain_id),
                description=entry.get("description", ""),
                path=Path(entry.get("path", "")),
            )
        return domains

    def _load_industries(self, path: Path) -> Dict[str, IndustryManifest]:
        data = self._load_yaml(path).get("industries", [])
        industries: Dict[str, IndustryManifest] = {}
        for entry in data:
            entry = entry or {}
            ind_id = entry.get("id")
            if not ind_id:
                continue
            industries[ind_id] = IndustryManifest(
                id=ind_id,
                name=entry.get("name", ind_id),
                description=entry.get("description", ""),
                protocols=list(entry.get("protocols", []) or []),
                services=list(entry.get("services", []) or []),
                profiles=[Path(p).stem for p in entry.get("profiles", [])],
                path=Path(entry.get("path", "")),
                default_instances=list(entry.get("default_instances", []) or []),
                start_instances=list(entry.get("start_instances", []) or []),
            )
        return industries

    def _load_profiles(self, base_dir: Path) -> Dict[str, ProfileManifest]:
        if not base_dir.exists():
            return {}
        profiles: Dict[str, ProfileManifest] = {}
        for pack_dir in base_dir.iterdir():
            if not pack_dir.is_dir():
                continue
            pack_id = pack_dir.name
            for profile_path in pack_dir.glob("*.yaml"):
                with profile_path.open("r", encoding="utf-8") as handle:
                    payload = yaml.safe_load(handle) or {}
                profile_id = payload.get("name") or profile_path.stem
                profiles[profile_id] = ProfileManifest(
                    id=profile_id,
                    pack_id=pack_id,
                    name=payload.get("name", profile_id),
                    description=payload.get("description", ""),
                    models=[Path(p) for p in payload.get("models", [])],
                    services=list(payload.get("services", []) or []),
                    path=profile_path,
                )
        return profiles
