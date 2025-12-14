# SPDX-License-Identifier: MIT
"""Command-line entrypoints for the installer."""

from __future__ import annotations

import argparse
import json

from pathlib import Path
import os
import shutil
import subprocess
import sys
from typing import Iterable, List, Optional

from .generator import DeploymentGenerator
from .manifest import ManifestLoader
from .selection import resolve_default_instances, resolve_model_ids, resolve_service_ids
from .wizard import InstallerWizard, WizardSelection


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="spx-installer",
        description="Interactive installer for SPX example packages.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    wizard_parser = subparsers.add_parser(
        "wizard", help="Launch the interactive console wizard."
    )
    wizard_parser.add_argument(
        "--catalog",
        type=str,
        default=None,
        help="Optional path to catalog directory (defaults to library/catalog).",
    )
    wizard_parser.add_argument(
        "--profiles",
        type=str,
        default=None,
        help="Optional path to profiles directory (defaults to profiles/).",
    )

    generate_parser = subparsers.add_parser(
        "generate",
        help="Generate deployment artifacts (interactive wizard by default; pass selectors to run non-interactively).",
    )
    generate_parser.add_argument(
        "--catalog",
        type=str,
        default=None,
        help="Optional path to catalog directory (defaults to library/catalog).",
    )
    generate_parser.add_argument(
        "--profiles",
        type=str,
        default=None,
        help="Optional path to profiles directory (defaults to profiles/).",
    )
    generate_parser.add_argument(
        "--output",
        type=str,
        default="build/spx-generated",
        help="Output directory for generated artifacts (default: build/spx-generated).",
    )
    generate_parser.add_argument(
        "--packages",
        action="append",
        default=[],
        metavar="PACK[,PACK...]",
        help="Non-interactive selection: one or more pack IDs (repeatable or comma-separated).",
    )
    generate_parser.add_argument(
        "--profile-ids",
        action="append",
        default=[],
        metavar="PROFILE[,PROFILE...]",
        help="Non-interactive selection: profile IDs (repeatable or comma-separated).",
    )
    generate_parser.add_argument(
        "--protocols",
        action="append",
        default=[],
        metavar="PROTO[,PROTO...]",
        help="Non-interactive selection: protocol filters (repeatable or comma-separated).",
    )
    generate_parser.add_argument(
        "--product-key",
        default=None,
        help="SPX product key (defaults to SPX_PRODUCT_KEY env var).",
    )
    generate_parser.add_argument(
        "--allow-missing-product-key",
        action="store_true",
        help="Allow generating artifacts without an SPX product key (writes REPLACE_ME).",
    )
    generate_parser.add_argument(
        "--with-ui",
        dest="install_spx_ui",
        action="store_true",
        default=None,
        help="Include SPX UI frontend container in the generated compose.",
    )
    generate_parser.add_argument(
        "--no-ui",
        dest="install_spx_ui",
        action="store_false",
        default=None,
        help="Do not include SPX UI frontend container in the generated compose.",
    )
    generate_parser.add_argument(
        "--with-examples",
        dest="install_examples",
        action="store_true",
        default=None,
        help="Enable bootstrap runner in generated start scripts (default in non-interactive mode).",
    )
    generate_parser.add_argument(
        "--no-examples",
        dest="install_examples",
        action="store_false",
        default=None,
        help="Disable bootstrap runner in generated start scripts.",
    )
    generate_parser.add_argument(
        "--print-selection",
        choices=["json"],
        default=None,
        help="Print the resolved selection to stdout.",
    )
    generate_parser.add_argument(
        "--start",
        action="store_true",
        help="Start the generated stack immediately (non-interactive; no prompt).",
    )
    generate_parser.add_argument(
        "--no-start",
        action="store_true",
        help="Do not prompt to start the stack after generating artifacts.",
    )

    bootstrap_parser = subparsers.add_parser(
        "bootstrap", help="Register models with a running SPX server."
    )
    bootstrap_parser.add_argument(
        "--bundle",
        required=True,
        help="Path to bundle.json produced by the installer",
    )
    bootstrap_parser.add_argument(
        "--api-url",
        default="http://localhost:8000",
        help="SPX server API base URL (default: %(default)s)",
    )
    bootstrap_parser.add_argument(
        "--skip-instances",
        action="store_true",
        help="Register models only (do not create instances from bundle.json).",
    )

    return parser


def _split_csv(values: Iterable[str]) -> List[str]:
    result: List[str] = []
    for raw in values:
        for item in str(raw).split(","):
            item = item.strip()
            if item:
                result.append(item)
    return result


def _resolve_product_key(
    *,
    explicit: Optional[str],
    allow_missing: bool,
) -> str:
    if explicit is not None and explicit.strip():
        return explicit.strip()
    env_value = os.environ.get("SPX_PRODUCT_KEY", "").strip()
    if env_value:
        return env_value
    if allow_missing:
        return "REPLACE_ME"
    raise SystemExit(
        "Missing SPX product key. Set SPX_PRODUCT_KEY or pass --product-key "
        "(or use --allow-missing-product-key to generate artifacts only)."
    )


def _build_noninteractive_selection(
    args: argparse.Namespace,
    *,
    index,
) -> WizardSelection:
    packages = _split_csv(getattr(args, "packages", []) or [])
    profile_ids = _split_csv(getattr(args, "profile_ids", []) or [])
    protocols = _split_csv(getattr(args, "protocols", []) or [])

    unknown_packages = [pkg for pkg in packages if pkg not in index.industries]
    if unknown_packages:
        raise SystemExit(f"Unknown pack id(s): {', '.join(sorted(set(unknown_packages)))}")

    unknown_profiles = [pid for pid in profile_ids if pid not in index.profiles]
    if unknown_profiles:
        raise SystemExit(f"Unknown profile id(s): {', '.join(sorted(set(unknown_profiles)))}")

    product_key = _resolve_product_key(
        explicit=getattr(args, "product_key", None),
        allow_missing=bool(getattr(args, "allow_missing_product_key", False)),
    )

    install_examples = (
        True if getattr(args, "install_examples", None) is None else bool(args.install_examples)
    )
    install_spx_ui = (
        False if getattr(args, "install_spx_ui", None) is None else bool(args.install_spx_ui)
    )

    model_ids = resolve_model_ids(packages, profile_ids, protocols, index)
    if packages and not model_ids:
        raise SystemExit(f"Selection for packages {packages!r} resolves to zero models; check catalog configuration.")

    service_ids = resolve_service_ids(model_ids, packages, profile_ids, index)
    unknown_services = [sid for sid in service_ids if sid not in index.services]
    if unknown_services:
        raise SystemExit(
            "Selection references unknown service id(s): "
            + ", ".join(sorted(set(unknown_services)))
        )

    return WizardSelection(
        packages=packages,
        profiles=profile_ids,
        protocols=protocols,
        install_examples=install_examples,
        install_spx_ui=install_spx_ui,
        offline_bundle=True,
        license_key=product_key,
        model_ids=model_ids,
        service_ids=service_ids,
    )


def _print_selection(selection: WizardSelection, *, index) -> None:
    payload = {
        "packages": selection.packages,
        "profiles": selection.profiles,
        "protocols": selection.protocols,
        "install_examples": bool(selection.install_examples),
        "install_spx_ui": bool(selection.install_spx_ui),
        "models": selection.model_ids,
        "services": selection.service_ids,
        "instances": resolve_default_instances(selection.packages, index),
        "product_key_present": bool(selection.license_key and selection.license_key != "REPLACE_ME"),
    }
    print(json.dumps(payload, indent=2, sort_keys=True))


def run(args: argparse.Namespace) -> int:
    if args.command == "wizard":
        loader = ManifestLoader(
            catalog_dir=None if getattr(args, "catalog", None) is None else args.catalog,
            profiles_dir=None if getattr(args, "profiles", None) is None else args.profiles,
        )
        wizard = InstallerWizard(loader=loader)
        wizard.run()
        return 0
    if args.command == "generate":
        info_stream = sys.stderr if getattr(args, "print_selection", None) else sys.stdout
        loader = ManifestLoader(
            catalog_dir=None if getattr(args, "catalog", None) is None else args.catalog,
            profiles_dir=None if getattr(args, "profiles", None) is None else args.profiles,
        )

        noninteractive = bool(
            (getattr(args, "packages", None) or [])
            or (getattr(args, "profile_ids", None) or [])
            or (getattr(args, "protocols", None) or [])
        )

        if noninteractive:
            index = loader.load()
            selection = _build_noninteractive_selection(args, index=index)
        else:
            wizard = InstallerWizard(loader=loader)
            selection = wizard.run()
            if wizard.index is None:
                raise RuntimeError("Manifest index unavailable after wizard run.")
            index = wizard.index

        generator = DeploymentGenerator(index)
        output_dir = Path(args.output)
        generator.generate(selection, output_dir)

        if getattr(args, "print_selection", None) == "json":
            _print_selection(selection, index=index)

        print(f"\nArtifacts generated in {output_dir}", file=info_stream)
        print("Next steps:", file=info_stream)
        print(f"  1. Update '{output_dir}/.env' with your SPX product key if needed.", file=info_stream)
        print(
            f"  2. Run '{output_dir}/spx-start.sh' (macOS/Linux) or 'pwsh {output_dir}/spx-start.ps1' (Windows) to start the stack.",
            file=info_stream,
        )
        print(
            f"  3. Use '{output_dir}/spx-stop.sh' or 'pwsh {output_dir}/spx-stop.ps1' to shut everything down.",
            file=info_stream,
        )

        if getattr(args, "start", False):
            _launch_stack(output_dir, stream=info_stream)
            return 0

        if noninteractive or getattr(args, "no_start", False):
            return 0

        launch = input("\nStart the stack now? [Y/n]: ").strip().lower()
        if launch in {"", "y", "yes"}:
            _launch_stack(output_dir, stream=info_stream)
        return 0
    if args.command == "bootstrap":
        from .bootstrap import bootstrap

        bootstrap(
            Path(args.bundle),
            args.api_url,
            skip_instances=bool(getattr(args, "skip_instances", False)),
        )
        return 0
    raise ValueError(f"Unsupported command: {args.command}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return run(args)


def _launch_stack(output_dir: Path, *, stream=sys.stdout) -> None:
    if os.name == "nt":
        script = output_dir / "spx-start.ps1"
        if not script.exists():
            print(f"[spx-installer] Cannot find {script}; skipping start.", file=stream)
            return
        shell = shutil.which("pwsh") or shutil.which("powershell")
        if not shell:
            print(
                "[spx-installer] Neither pwsh nor powershell is available; please start manually.",
                file=stream,
            )
            return
        cmd = [shell, "-ExecutionPolicy", "Bypass", "-File", str(script)]
    else:
        script = output_dir / "spx-start.sh"
        if not script.exists():
            print(f"[spx-installer] Cannot find {script}; skipping start.", file=stream)
            return
        cmd = [str(script)]

    print(f"[spx-installer] Launching stack via {script} ...", file=stream)
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as exc:
        print(
            f"[spx-installer] Start script exited with {exc.returncode}. Please inspect the logs.",
            file=stream,
        )


if __name__ == "__main__":
    raise SystemExit(main())
