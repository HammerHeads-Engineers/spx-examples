# SPDX-License-Identifier: MIT
"""Console wizard guiding the user through package selection."""

from __future__ import annotations

import os
from dataclasses import dataclass
from shutil import get_terminal_size
from typing import Dict, List, Sequence

from .manifest import IndustryManifest, ManifestIndex, ManifestLoader
from .selection import resolve_model_ids, resolve_service_ids
from . import ui


@dataclass(frozen=True)
class WizardSelection:
    packages: List[str]
    profiles: List[str]
    protocols: List[str]
    install_examples: bool
    install_spx_ui: bool
    offline_bundle: bool
    license_key: str
    model_ids: List[str]
    service_ids: List[str]


class InstallerWizard:
    """Text-based wizard operating purely in the console."""

    def __init__(self, loader: ManifestLoader | None = None) -> None:
        self.loader = loader or ManifestLoader()
        self.index: ManifestIndex | None = None

    # Public API -------------------------------------------------------------
    def run(self) -> WizardSelection:
        index = self.loader.load()
        self.index = index
        self._print_banner()
        packages, protocol_filters = self._prompt_packages(index.industries, index)
        profiles = self._prompt_profiles(packages, index)
        install_examples = self._prompt_yes_no("\nInstall bundled example models/tests? [Y/n]: ", default=True)
        install_spx_ui = self._prompt_yes_no("Include SPX UI frontend container? [Y/n]: ", default=True)
        offline_bundle = self._prompt_yes_no(
            "Prepare offline installation bundle instead of immediate launch? [y/N]: ",
            default=False,
        )
        license_key = self._prompt_license_key()

        model_ids = resolve_model_ids(packages, profiles, protocol_filters, index)
        service_ids = resolve_service_ids(model_ids, packages, profiles, index)

        self._print_summary(
            packages,
            profiles,
            protocol_filters,
            install_examples,
            install_spx_ui,
            offline_bundle,
            license_key,
            model_ids,
            service_ids,
            index,
        )

        return WizardSelection(
            packages=packages,
            profiles=profiles,
            protocols=protocol_filters,
            install_examples=install_examples,
            install_spx_ui=install_spx_ui,
            offline_bundle=offline_bundle,
            license_key=license_key,
            model_ids=model_ids,
            service_ids=service_ids,
        )

    # Internal helpers -------------------------------------------------------
    def _print_banner(self) -> None:
        width = max(60, min(get_terminal_size((80, 20)).columns, 120))
        bar = ui.hr("=", width)
        print(bar)
        print(ui.heading(" SPX Installation Wizard ".center(width)))
        print(bar)
        print(
            ui.accent(
                "Select packages or protocols, then customize optional components.\n"
            )
        )

    def _prompt_packages(
        self,
        industries: Dict[str, IndustryManifest],
        index: ManifestIndex,
    ) -> tuple[List[str], List[str]]:
        entries = list(industries.values())
        entries.sort(key=lambda ind: ind.name.lower())

        print(ui.heading("Available packages:\n"))
        for idx, ind in enumerate(entries, start=1):
            print(f"  [{ui.accent(str(idx))}] {ui.heading(ind.name)}")
            print(f"      {ind.description}")
            if ind.protocols:
                print(f"      Protocols: {', '.join(ind.protocols)}")
            if ind.services:
                print(f"      Services: {', '.join(ind.services)}")
            print()

        print(f"  [{ui.accent('0')}] {ui.heading('Choose by protocols instead')}\n")

        while True:
            raw = input("Enter package numbers (comma-separated, e.g. 1,3 or 0 for protocols, q to quit): ").strip()
            self._check_quit(raw)
            if raw in {"0", "p", "P"}:
                protocols = self._prompt_protocols(index)
                if protocols:
                    return [], protocols
                print(ui.warn("  Please select at least one protocol."))
                continue
            try:
                values = [
                    int(token)
                    for token in raw.split(",")
                    if token.strip()
                ]
            except ValueError:
                print(ui.warn("  Invalid input. Please enter numbers separated by commas."))
                continue
            if not values:
                print(ui.warn("  Please select at least one entry."))
                continue
            if any(v < 1 or v > len(entries) for v in values):
                print(ui.warn(f"  Values must be between 1 and {len(entries)}."))
                continue
            packages = [entries[i - 1].id for i in sorted(set(values))]
            return packages, []

    def _prompt_profiles(
        self,
        packages: Sequence[str],
        index: ManifestIndex,
    ) -> List[str]:
        available_profiles = [
            profile_id
            for profile_id, profile in index.profiles.items()
            if profile.pack_id in packages
        ]
        if not available_profiles:
            return []

        print(ui.heading("\nQuickstart profiles matching your packages:\n"))
        for idx, profile_id in enumerate(sorted(available_profiles), start=1):
            profile = index.profiles[profile_id]
            print(f"  [{ui.accent(str(idx))}] {ui.heading(profile.name)} (pack: {profile.pack_id})")
            print(f"      {profile.description}")
            if profile.services:
                print(f"      Extra services: {', '.join(profile.services)}")
            print()

        choices = self._prompt_indices(
            "Select quickstart profiles (comma-separated, ENTER to skip, q to quit): ",
            len(available_profiles),
            allow_empty=True,
        )
        return [sorted(available_profiles)[i - 1] for i in choices]

    def _prompt_yes_no(self, prompt: str, *, default: bool) -> bool:
        while True:
            raw = input(prompt).strip().lower()
            self._check_quit(raw)
            if not raw:
                return default
            if raw in {"y", "yes"}:
                return True
            if raw in {"n", "no"}:
                return False
            print(ui.warn("  Please enter 'y' or 'n'."))

    def _prompt_protocols(self, index: ManifestIndex) -> List[str]:
        protocol_set = {
            proto
            for model in index.models.values()
            for proto in model.protocols
        }
        protocol_set |= {
            svc.protocol
            for svc in index.services.values()
            if svc.protocol
        }
        if not protocol_set:
            print(ui.warn("No protocols available."))
            return []

        sorted_protocols = sorted(protocol_set)
        print(ui.heading("\nAvailable protocols:\n"))
        for idx, proto in enumerate(sorted_protocols, start=1):
            print(f"  [{ui.accent(str(idx))}] {proto}")
        choices = self._prompt_indices(
            "Select protocols (comma-separated, q to quit): ",
            len(sorted_protocols),
            allow_empty=False,
        )
        return [sorted_protocols[i - 1] for i in choices]

    def _prompt_license_key(self) -> str:
        env_value = os.environ.get("SPX_PRODUCT_KEY", "").strip()
        if env_value:
            print(ui.accent(f"\nDetected SPX_PRODUCT_KEY in environment: {env_value}"))
            return env_value

        print(ui.heading("\nSPX Product Key"))
        while True:
            raw = input("Enter SPX product key (required, q to quit): ").strip()
            self._check_quit(raw)
            if raw:
                return raw
            print(ui.warn("  Product key cannot be empty."))

    def _check_quit(self, raw: str) -> None:
        if raw.lower() in {"q", "quit"}:
            print(ui.warn("Exiting wizard."))
            raise SystemExit(0)

    def _prompt_indices(
        self,
        prompt: str,
        max_index: int,
        *,
        allow_empty: bool,
    ) -> List[int]:
        while True:
            raw = input(prompt).strip()
            self._check_quit(raw)
            if not raw and allow_empty:
                return []
            try:
                values = [
                    int(token)
                    for token in raw.split(",")
                    if token.strip()
                ]
            except ValueError:
                print(ui.warn("  Invalid input. Please enter numbers separated by commas."))
                continue
            if not values:
                print(ui.warn("  Please select at least one entry."))
                continue
            if any(v < 1 or v > max_index for v in values):
                print(ui.warn(f"  Values must be between 1 and {max_index}."))
                continue
            return sorted(set(values))

    def _print_summary(
        self,
        packages: Sequence[str],
        profiles: Sequence[str],
        protocols: Sequence[str],
        install_examples: bool,
        install_spx_ui: bool,
        offline_bundle: bool,
        license_key: str,
        model_ids: Sequence[str],
        service_ids: Sequence[str],
        index: ManifestIndex,
    ) -> None:
        print(ui.heading("\nSummary"))
        print(ui.hr("-"))
        print("Packages:")
        if packages:
            for pkg in packages:
                manifest = index.industries[pkg]
                print(f"  • {ui.heading(manifest.name)}")
        else:
            print("  • (none selected)")
        if profiles:
            print("\nProfiles:")
            for profile_id in profiles:
                profile = index.profiles[profile_id]
                print(f"  • {ui.heading(profile.name)} (pack: {profile.pack_id})")
        if protocols:
            print("\nProtocols:")
            for proto in protocols:
                print(f"  • {proto}")
        print(f"\nInstall examples: {ui.success('yes') if install_examples else ui.warn('no')}")
        print(f"Include SPX UI: {ui.success('yes') if install_spx_ui else ui.warn('no')}")
        print(f"Offline bundle: {ui.success('yes') if offline_bundle else ui.warn('no')}")
        print(f"SPX product key: {ui.heading(license_key or 'N/A')}")
        print("\nModels:")
        for model_id in model_ids:
            manifest = index.models[model_id]
            print(f"  • {manifest.name} [{', '.join(manifest.protocols)}]")
        print("\nServices:")
        for service_id in service_ids:
            manifest = index.services[service_id]
            deployment = manifest.deployment.runtime if manifest.deployment else "docker"
            print(f"  • {manifest.name} ({deployment})")
