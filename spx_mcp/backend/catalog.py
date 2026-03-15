# SPDX-License-Identifier: MIT
"""Repository catalog helpers for SPX models, packs, and profiles."""

from __future__ import annotations

from functools import cached_property
from pathlib import Path
from typing import Any, Dict, List, Optional

from installer.manifest import ManifestLoader


class RepoCatalog:
    """Thin adapter over the installer manifest index for repo-aware MCP tools."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = Path(repo_root).resolve()

    @cached_property
    def index(self):
        loader = ManifestLoader(
            catalog_dir=self.repo_root / "library" / "catalog",
            profiles_dir=self.repo_root / "profiles",
        )
        return loader.load()

    def list_packs(self) -> List[Dict[str, Any]]:
        packs: List[Dict[str, Any]] = []
        for pack_id, manifest in sorted(self.index.industries.items()):
            packs.append(
                {
                    "id": pack_id,
                    "name": manifest.name,
                    "description": manifest.description,
                    "protocols": list(manifest.protocols),
                    "services": list(manifest.services),
                    "profiles": list(manifest.profiles),
                }
            )
        return packs

    def list_profiles(self, pack_id: Optional[str] = None) -> List[Dict[str, Any]]:
        profiles: List[Dict[str, Any]] = []
        for profile_id, manifest in sorted(self.index.profiles.items()):
            if pack_id and manifest.pack_id != pack_id:
                continue
            profiles.append(
                {
                    "id": profile_id,
                    "pack_id": manifest.pack_id,
                    "name": manifest.name,
                    "description": manifest.description,
                    "models": [str(path) for path in manifest.models],
                    "services": list(manifest.services),
                }
            )
        return profiles

    def find_models(
        self,
        *,
        query: Optional[str] = None,
        pack_id: Optional[str] = None,
        profile_id: Optional[str] = None,
        protocol: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        query_text = (query or "").strip().lower()
        results: List[Dict[str, Any]] = []
        for model_id in sorted(self.index.models):
            manifest = self.index.models[model_id]
            if pack_id and pack_id not in manifest.packages:
                continue
            if profile_id and profile_id not in manifest.profiles:
                continue
            if protocol and protocol not in manifest.protocols:
                continue
            haystacks = [
                model_id,
                manifest.name,
                str(manifest.path),
                manifest.domain,
                manifest.domain_group,
                manifest.device_class,
                manifest.vendor,
                " ".join(manifest.protocols),
                " ".join(manifest.packages),
                " ".join(manifest.profiles),
            ]
            if query_text and query_text not in " ".join(haystacks).lower():
                continue
            results.append(self._model_summary(model_id))
        return results

    def get_model(self, model_id: str) -> Dict[str, Any]:
        if model_id not in self.index.models:
            raise KeyError(f"Unknown model id: {model_id}")
        return self._model_summary(model_id)

    def get_model_path(self, model_id: str) -> Path:
        model = self.get_model(model_id)
        return self.repo_root / model["path"]

    def _model_summary(self, model_id: str) -> Dict[str, Any]:
        manifest = self.index.models[model_id]
        return {
            "id": model_id,
            "name": manifest.name,
            "path": str(manifest.path),
            "domain": manifest.domain,
            "domain_group": manifest.domain_group,
            "device_class": manifest.device_class,
            "vendor": manifest.vendor,
            "protocols": list(manifest.protocols),
            "services": list(manifest.services),
            "packages": list(manifest.packages),
            "profiles": list(manifest.profiles),
        }
