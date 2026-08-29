# SPDX-License-Identifier: MIT
"""Console wizard guiding the user through package selection."""

from __future__ import annotations

import getpass
import os
import re
from dataclasses import dataclass
from shutil import get_terminal_size
from textwrap import shorten
from typing import Dict, List, Sequence

from . import paths, ui
from .manifest import IndustryManifest, ManifestIndex, ManifestLoader
from .selection import (
    apply_platform_compatibility,
    current_platform_name,
    resolve_default_instances,
    resolve_model_ids,
    resolve_protocol_model_ids,
    resolve_protocol_service_ids,
    resolve_service_ids,
)

DEFAULT_PROTOCOLS = ("modbus", "ascii", "scpi")
PROTOCOL_ALIASES = {"ascii": "scpi"}
PROTOCOL_LABELS = {"scpi": "scpi (ASCII)"}
PROTOCOL_BADGE_LABELS = {
    "ascii": "ASCII",
    "opcua": "OPC UA",
    "modbus": "Modbus",
    "mqtt": "MQTT",
    "bacnet": "BACnet",
    "knx": "KNX",
    "matter": "Matter",
    "lwm2m": "LwM2M",
    "http": "HTTP",
    "ocpp": "OCPP",
    "ble": "BLE",
    "scpi": "SCPI",
}
PACKAGE_PROTOCOL_HIGHLIGHTS = {
    "embedded_lab_pack": ("ascii", "scpi", "ble", "modbus"),
    "industrial_iiot_pack": ("opcua", "modbus", "mqtt"),
    "smart_building_pack": ("bacnet", "knx", "mqtt"),
}
PACKAGE_DISPLAY_SUMMARIES = {
    "embedded_lab_pack": "Modbus TCP, SCPI, BLE, MQTT/LwM2M for firmware CI and hardware-in-the-loop labs.",
}
THIRD_PARTY_SERVICE_NOTICES = {
    "mqtt_broker": "MQTT Broker pulls Eclipse Mosquitto under separate open-source license terms.",
    "lwm2m_server": "LwM2M Server pulls Eclipse Leshan under separate open-source license terms.",
    "knx_gateway": (
        "KNX Gateway pulls knxd-based container images under separate open-source license terms; "
        "review redistribution obligations before mirroring or bundling them."
    ),
    "homeassistant_bridge": "Home Assistant Bridge pulls Home Assistant under separate open-source license terms.",
    "matter_server": "Matter Server pulls python-matter-server under separate open-source license terms.",
}


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
    instances: List[Dict[str, str]]
    start_instances: List[str]


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
        protocol_only = bool(protocol_filters) and not packages
        profiles: List[str] = []
        install_models = False
        install_instances = False
        start_instances: List[str] = []
        model_ids: List[str] = []
        service_ids: List[str] = []
        instances: List[Dict[str, str]] = []

        if protocol_only:
            install_models = self._prompt_yes_no(
                "\nInstall/register compatible models? [Y/n]: ",
                default=True,
            )
            if install_models:
                model_ids = resolve_protocol_model_ids(protocol_filters, index)
            service_ids = self._prompt_protocol_services(protocol_filters, index)
            self._warn_for_disabled_protocol_services(model_ids, service_ids, index)
        else:
            profiles = self._prompt_profiles(packages, index)
            selection_label = (
                "selected packages and profiles" if profiles else "selected packages"
            )
            install_models = self._prompt_yes_no(
                f"\nAdd models from {selection_label}? [Y/n]: ",
                default=True,
            )
            if install_models:
                install_instances = self._prompt_yes_no(
                    "Add default instances? [y/N]: ",
                    default=False,
                )
                if install_instances:
                    start_instances = self._prompt_start_instances(packages, index)
        install_spx_ui = self._prompt_yes_no(
            "Include SPX UI frontend container? [Y/n]: ", default=True
        )
        start_now = self._prompt_yes_no(
            "Start the stack immediately after generation? [Y/n]: ",
            default=True,
        )
        offline_bundle = not start_now
        license_key = self._prompt_license_key()

        if not protocol_only:
            model_protocol_filters = protocol_filters if not packages else []
            model_ids = (
                resolve_model_ids(packages, profiles, model_protocol_filters, index)
                if install_models
                else []
            )
            service_ids = resolve_service_ids(model_ids, packages, profiles, index)
            instances = (
                resolve_default_instances(packages, index) if install_instances else []
            )
            if install_instances:
                allowed = {
                    entry.get("instance_key")
                    for entry in instances
                    if entry.get("instance_key")
                }
                start_instances = [key for key in start_instances if key in allowed]
            if install_instances and (
                "smart_building_pack" in packages
                or "industrial_iiot_pack" in packages
                or "embedded_lab_pack" in packages
            ):
                allowed = set(start_instances)
                instances = [
                    entry for entry in instances if entry.get("instance_key") in allowed
                ]

        compatibility = apply_platform_compatibility(
            model_ids=model_ids,
            service_ids=service_ids,
            instances=instances,
            start_instances=start_instances,
            index=index,
        )
        model_ids = compatibility.model_ids
        service_ids = compatibility.service_ids
        instances = compatibility.instances
        start_instances = compatibility.start_instances

        if compatibility.warnings:
            print(ui.warn("\nPlatform compatibility adjustments:"))
            for warning in compatibility.warnings:
                print(f"  - {warning}")

        runtime_notices = self._build_runtime_notices(
            service_ids=service_ids,
            install_spx_ui=install_spx_ui,
            index=index,
        )
        if runtime_notices:
            print(ui.warn("\nRuntime & third-party notices:"))
            for notice in runtime_notices:
                print(f"  - {notice}")
            self._prompt_continue(
                "\nPress ENTER to continue after reviewing these notices (or q to quit): "
            )

        self._print_summary(
            packages,
            profiles,
            protocol_filters,
            install_models,
            install_instances,
            install_spx_ui,
            start_now,
            license_key,
            model_ids,
            service_ids,
            instances,
            start_instances,
            index,
        )

        return WizardSelection(
            packages=packages,
            profiles=profiles,
            protocols=protocol_filters,
            install_examples=install_models,
            install_spx_ui=install_spx_ui,
            offline_bundle=offline_bundle,
            license_key=license_key,
            model_ids=model_ids,
            service_ids=service_ids,
            instances=instances,
            start_instances=start_instances,
        )

    # Internal helpers -------------------------------------------------------
    def _print_banner(self) -> None:
        width = max(60, min(get_terminal_size((80, 20)).columns, 120))
        bar = ui.hr("=", width)
        version = self._resolve_installer_version()
        print(bar)
        print(ui.heading(" SPX Installation Wizard ".center(width)))
        print(ui.accent(f" Version {version} ".center(width)))
        print(bar)
        print(
            ui.accent(
                "Select packages or protocols, then customize optional components.\n"
            )
        )

    def _resolve_installer_version(self) -> str:
        pyproject = paths.repo_root() / "pyproject.toml"
        if not pyproject.exists():
            return "dev"

        content = pyproject.read_text(encoding="utf-8")
        match = re.search(r'^\s*version\s*=\s*"([^"]+)"', content, flags=re.MULTILINE)
        if not match:
            return "dev"
        return match.group(1).strip() or "dev"

    def _available_protocols(self, index: ManifestIndex) -> List[str]:
        protocol_set = {
            proto for model in index.models.values() for proto in model.protocols
        }
        protocol_set |= {
            svc.protocol for svc in index.services.values() if svc.protocol
        }
        return sorted(protocol_set)

    def _resolve_default_protocols(self, index: ManifestIndex) -> List[str]:
        available = set(self._available_protocols(index))
        resolved: List[str] = []
        for proto in DEFAULT_PROTOCOLS:
            canonical = PROTOCOL_ALIASES.get(proto, proto)
            if canonical in available and canonical not in resolved:
                resolved.append(canonical)
        return resolved

    def _format_protocol_label(self, protocol: str) -> str:
        return PROTOCOL_LABELS.get(protocol, protocol)

    def _prompt_packages(
        self,
        industries: Dict[str, IndustryManifest],
        index: ManifestIndex,
    ) -> tuple[List[str], List[str]]:
        entries = list(industries.values())
        entries.sort(key=lambda ind: ind.name.lower())
        default_protocols = self._resolve_default_protocols(index)
        default_protocol_label = ", ".join(
            self._format_protocol_label(p) for p in default_protocols
        )
        width = max(60, min(get_terminal_size((80, 20)).columns, 120))

        print(ui.heading("Available packages:\n"))
        for idx, ind in enumerate(entries, start=1):
            print(
                f"  [{ui.accent(str(idx))}] {ui.heading(ind.name)}"
                f" {self._format_package_overview(ind, width)}"
            )

        if default_protocol_label:
            print(
                f"  [{ui.accent('0')}] {ui.heading('Choose by protocols instead')} "
                f"{ui.accent(f'(default: {default_protocol_label})')}\n"
            )
        else:
            print(f"  [{ui.accent('0')}] {ui.heading('Choose by protocols instead')}\n")

        while True:
            raw = input(
                "Enter package numbers (comma-separated, ENTER for default protocols, 0 for protocols, q to quit): "
            ).strip()
            self._check_quit(raw)
            if not raw:
                if default_protocols:
                    return [], default_protocols
                print(
                    ui.warn(
                        "  Default protocols are unavailable; please select an entry."
                    )
                )
                continue
            if raw in {"0", "p", "P"}:
                protocols = self._prompt_protocols(index)
                if protocols:
                    return [], protocols
                print(ui.warn("  Please select at least one protocol."))
                continue
            try:
                values = [int(token) for token in raw.split(",") if token.strip()]
            except ValueError:
                print(
                    ui.warn(
                        "  Invalid input. Please enter numbers separated by commas."
                    )
                )
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
        width = max(60, min(get_terminal_size((80, 20)).columns, 120))

        print(ui.heading("\nOptional starter scenarios for your package:\n"))
        for idx, profile_id in enumerate(sorted(available_profiles), start=1):
            profile = index.profiles[profile_id]
            print(
                f"  [{ui.accent(str(idx))}] {ui.heading(profile.name)} "
                f"(pack: {profile.pack_id}) {self._format_profile_overview(profile, width)}"
            )

        while True:
            raw = input(
                "Select starter scenarios (comma-separated, ENTER to use package defaults only, a for all, q to quit): "
            ).strip()
            self._check_quit(raw)
            if not raw:
                return []
            if raw.lower() in {"a", "all"}:
                return sorted(available_profiles)
            try:
                values = [int(token) for token in raw.split(",") if token.strip()]
            except ValueError:
                print(
                    ui.warn(
                        "  Invalid input. Please enter numbers separated by commas, or 'a' for all."
                    )
                )
                continue
            if not values:
                print(ui.warn("  Please select at least one entry."))
                continue
            if any(v < 1 or v > len(available_profiles) for v in values):
                print(
                    ui.warn(
                        f"  Values must be between 1 and {len(available_profiles)}."
                    )
                )
                continue
            return [sorted(available_profiles)[i - 1] for i in sorted(set(values))]

    def _prompt_start_instances(
        self,
        packages: Sequence[str],
        index: ManifestIndex,
    ) -> List[str]:
        if not packages:
            return []

        selected: List[str] = []
        seen: set[str] = set()
        for pkg_id in packages:
            manifest = index.industries.get(pkg_id)
            if not manifest or not manifest.start_instances:
                continue
            start_keys = [
                str(entry).strip()
                for entry in manifest.start_instances
                if str(entry).strip()
            ]
            if not start_keys:
                continue
            instance_models = {
                entry.get("instance"): entry.get("model")
                for entry in manifest.default_instances
                if isinstance(entry, dict) and entry.get("instance")
            }
            print(ui.heading(f"\nInstances to start for {manifest.name}:"))
            for instance_key in start_keys:
                model_id = instance_models.get(instance_key)
                if model_id:
                    print(f"  • {instance_key} ({model_id})")
                else:
                    print(f"  • {instance_key}")
            if self._prompt_yes_no(
                "Start these instances after creation? [Y/n]: ", default=True
            ):
                for instance_key in start_keys:
                    if instance_key in seen:
                        continue
                    seen.add(instance_key)
                    selected.append(instance_key)
        return selected

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

    def _prompt_continue(self, prompt: str) -> None:
        raw = input(prompt).strip()
        self._check_quit(raw)

    def _prompt_protocols(self, index: ManifestIndex) -> List[str]:
        sorted_protocols = self._available_protocols(index)
        if not sorted_protocols:
            print(ui.warn("No protocols available."))
            return []

        default_protocols = self._resolve_default_protocols(index)
        default_protocol_label = ", ".join(
            self._format_protocol_label(p) for p in default_protocols
        )

        print(ui.heading("\nAvailable protocols:\n"))
        for idx, proto in enumerate(sorted_protocols, start=1):
            print(f"  [{ui.accent(str(idx))}] {self._format_protocol_label(proto)}")
        while True:
            prompt = "Select protocols (comma-separated, ENTER for default"
            if default_protocol_label:
                prompt += f" {default_protocol_label}"
            prompt += ", q to quit): "
            choices = self._prompt_indices(
                prompt,
                len(sorted_protocols),
                allow_empty=True,
            )
            if not choices:
                if default_protocols:
                    return default_protocols
                print(ui.warn("  Please select at least one protocol."))
                continue
            return [sorted_protocols[i - 1] for i in choices]

    def _prompt_protocol_services(
        self,
        protocols: Sequence[str],
        index: ManifestIndex,
    ) -> List[str]:
        if not protocols:
            return []

        candidate_ids = resolve_protocol_service_ids(protocols, index)
        candidates = [index.services[service_id] for service_id in candidate_ids]
        if not candidates:
            return []

        candidates.sort(key=lambda svc: (svc.protocol or "", svc.name.lower()))
        print(ui.heading("\nServices matching selected protocols:\n"))
        for idx, service in enumerate(candidates, start=1):
            runtime = service.deployment.runtime if service.deployment else "docker"
            ports = ", ".join(f"{port.host}/{port.transport}" for port in service.ports)
            print(
                f"  [{ui.accent(str(idx))}] {ui.heading(service.name)} "
                f"({service.protocol}, {runtime})"
            )
            if service.description:
                print(f"      {service.description}")
            if ports:
                print(f"      Ports: {ports}")
            print()

        while True:
            raw = input(
                "Select services to enable (comma-separated, ENTER for all, none for none, q to quit): "
            ).strip()
            self._check_quit(raw)
            if not raw:
                return [service.id for service in candidates]
            if raw.lower() in {"n", "none"}:
                return []
            if raw.lower() in {"a", "all"}:
                return [service.id for service in candidates]
            try:
                choices = [int(token) for token in raw.split(",") if token.strip()]
            except ValueError:
                print(
                    ui.warn("  Invalid input. Enter numbers, 'none', or ENTER for all.")
                )
                continue
            if not choices or any(
                choice < 1 or choice > len(candidates) for choice in choices
            ):
                print(ui.warn(f"  Values must be between 1 and {len(candidates)}."))
                continue
            return [candidates[index - 1].id for index in sorted(set(choices))]

    def _warn_for_disabled_protocol_services(
        self,
        model_ids: Sequence[str],
        service_ids: Sequence[str],
        index: ManifestIndex,
    ) -> None:
        """Warn when selected models reference a service disabled in protocol mode."""

        selected_services = set(service_ids)
        missing_services = sorted(
            {
                service_id
                for model_id in model_ids
                for service_id in (
                    index.models.get(model_id).services
                    if index.models.get(model_id)
                    else []
                )
                if service_id not in selected_services
            }
        )
        if not missing_services:
            return

        print(ui.warn("\nSome selected models reference disabled local services:"))
        for service_id in missing_services:
            service = index.services.get(service_id)
            service_name = service.name if service is not None else service_id
            print(
                f"  - {service_name} ({service_id}) is disabled; configure an external "
                "endpoint separately before using dependent models."
            )

    def _prompt_license_key(self) -> str:
        env_value = os.environ.get("SPX_PRODUCT_KEY", "").strip()
        if env_value:
            masked = self._mask_secret(env_value)
            print(ui.accent(f"\nDetected SPX_PRODUCT_KEY in environment: {masked}"))
            return env_value

        print(ui.heading("\nSPX Product Key"))
        while True:
            raw = getpass.getpass(
                "Enter SPX product key (required, q to quit): "
            ).strip()
            self._check_quit(raw)
            if raw:
                return raw
            print(ui.warn("  Product key cannot be empty."))

    def _check_quit(self, raw: str) -> None:
        if raw.lower() in {"q", "quit"}:
            print(ui.warn("Exiting wizard."))
            raise SystemExit(0)

    def _mask_secret(self, value: str, *, visible_tail: int = 4) -> str:
        clean = value.strip()
        if not clean:
            return "N/A"
        if len(clean) <= visible_tail:
            return "*" * len(clean)
        return f"{'*' * (len(clean) - visible_tail)}{clean[-visible_tail:]}"

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
                values = [int(token) for token in raw.split(",") if token.strip()]
            except ValueError:
                print(
                    ui.warn(
                        "  Invalid input. Please enter numbers separated by commas."
                    )
                )
                continue
            if not values:
                print(ui.warn("  Please select at least one entry."))
                continue
            if any(v < 1 or v > max_index for v in values):
                print(ui.warn(f"  Values must be between 1 and {max_index}."))
                continue
            return sorted(set(values))

    def _format_package_overview(self, manifest: IndustryManifest, width: int) -> str:
        desc = PACKAGE_DISPLAY_SUMMARIES.get(manifest.id, manifest.description or "")
        desc = " ".join(str(desc).split())
        badges = ", ".join(self._package_protocol_badges(manifest))
        counts = f"{badges} | {len(manifest.protocols)} protocols, {len(manifest.services)} services"
        return self._format_compact_overview(desc, counts, width)

    def _format_profile_overview(self, profile, width: int) -> str:
        desc = " ".join(str(profile.description or "").split())
        counts = f"{len(profile.models)} models, {len(profile.services)} extra services"
        return self._format_compact_overview(desc, counts, width)

    def _format_compact_overview(
        self, description: str, counts: str, width: int
    ) -> str:
        suffix = f" [{counts}]"
        available = max(20, width - len(suffix) - 12)
        compact_description = shorten(description, width=available, placeholder="...")
        if not compact_description:
            return suffix
        return f"- {compact_description}{suffix}"

    def _package_protocol_badges(self, manifest: IndustryManifest) -> List[str]:
        preferred = PACKAGE_PROTOCOL_HIGHLIGHTS.get(manifest.id)
        protocol_ids: List[str]
        if preferred:
            protocol_ids = [
                proto
                for proto in preferred
                if self._protocol_present(proto, manifest.protocols)
            ]
        else:
            protocol_ids = list(manifest.protocols[:3])
        return [
            PROTOCOL_BADGE_LABELS.get(proto, proto.upper()) for proto in protocol_ids
        ]

    def _protocol_present(
        self, protocol: str, available_protocols: Sequence[str]
    ) -> bool:
        if protocol in available_protocols:
            return True
        alias_target = PROTOCOL_ALIASES.get(protocol)
        return bool(alias_target and alias_target in available_protocols)

    def _build_runtime_notices(
        self,
        *,
        service_ids: Sequence[str],
        install_spx_ui: bool,
        index: ManifestIndex,
    ) -> List[str]:
        notices: List[str] = []
        seen: set[str] = set()
        normalized_platform = current_platform_name()

        if normalized_platform in {"windows", "macos"}:
            notices.append(
                "SPX runs as a Docker-based stack. Docker Desktop is required on this platform and "
                "is licensed separately by Docker; some organizations need a paid subscription."
            )
        else:
            notices.append(
                "SPX runs as a Docker-based stack. Make sure Docker Engine and Compose are installed "
                "before starting the generated environment."
            )

        if install_spx_ui:
            notices.append(
                "SPX UI is installed as part of the generated container stack and starts through Docker."
            )

        for service_id in service_ids:
            notice = THIRD_PARTY_SERVICE_NOTICES.get(service_id)
            if notice and notice not in seen:
                notices.append(notice)
                seen.add(notice)

            manifest = index.services.get(service_id)
            deployment = manifest.deployment if manifest is not None else None
            if deployment is None or deployment.runtime != "native":
                continue

            instruction = (deployment.instructions or {}).get(normalized_platform)
            if not instruction:
                continue

            native_notice = f"{manifest.name} requires host-side setup on {normalized_platform}: {instruction}"
            if native_notice not in seen:
                notices.append(native_notice)
                seen.add(native_notice)

        return notices

    def _print_summary(
        self,
        packages: Sequence[str],
        profiles: Sequence[str],
        protocols: Sequence[str],
        install_models: bool,
        install_instances: bool,
        install_spx_ui: bool,
        start_now: bool,
        license_key: str,
        model_ids: Sequence[str],
        service_ids: Sequence[str],
        instances: Sequence[Dict[str, str]],
        start_instances: Sequence[str],
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
                print(f"  • {self._format_protocol_label(proto)}")
        print(
            f"\nInstall models: {ui.success('yes') if install_models else ui.warn('no')}"
        )
        print(
            f"Install instances: {ui.success('yes') if install_instances else ui.warn('no')}"
        )
        print(
            f"Include SPX UI: {ui.success('yes') if install_spx_ui else ui.warn('no')}"
        )
        print(f"Start stack now: {ui.success('yes') if start_now else ui.warn('no')}")
        print(f"SPX product key: {ui.heading(self._mask_secret(license_key))}")
        print("\nModels:")
        for model_id in model_ids:
            manifest = index.models[model_id]
            print(f"  • {manifest.name} [{', '.join(manifest.protocols)}]")
        print("\nDefault instances:")
        if instances:
            for entry in instances:
                instance_key = entry.get("instance_key", "")
                model_id = entry.get("model_id", "")
                if instance_key and model_id:
                    print(f"  • {instance_key} ({model_id})")
                elif instance_key:
                    print(f"  • {instance_key}")
        else:
            print("  • (none selected)")
        print("\nInstances to start:")
        if start_instances:
            for instance_key in start_instances:
                print(f"  • {instance_key}")
        else:
            print("  • (none selected)")
        print("\nServices:")
        if service_ids:
            for service_id in service_ids:
                manifest = index.services[service_id]
                deployment = (
                    manifest.deployment.runtime if manifest.deployment else "docker"
                )
                print(f"  • {manifest.name} ({deployment})")
        else:
            print("  • (none selected)")
