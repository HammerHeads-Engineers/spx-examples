# SPDX-License-Identifier: MIT
"""Command-line entrypoints for the installer."""

from __future__ import annotations

import argparse

from pathlib import Path
import os
import shutil
import subprocess

from .generator import DeploymentGenerator
from .manifest import ManifestLoader
from .wizard import InstallerWizard


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
        "generate", help="Run wizard and generate deployment artifacts."
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

    return parser


def run(args: argparse.Namespace) -> int:
    if args.command in {"wizard", "generate"}:
        loader = ManifestLoader(
            catalog_dir=None if getattr(args, "catalog", None) is None else args.catalog,
            profiles_dir=None if getattr(args, "profiles", None) is None else args.profiles,
        )
        wizard = InstallerWizard(loader=loader)
        selection = wizard.run()
        if args.command == "generate":
            if wizard.index is None:
                raise RuntimeError("Manifest index unavailable after wizard run.")
            generator = DeploymentGenerator(wizard.index)
            output_dir = Path(args.output)
            generator.generate(selection, output_dir)
            print(f"\nArtifacts generated in {output_dir}")
            print("Next steps:")
            print(f"  1. Update '{output_dir}/.env' with your SPX product key if needed.")
            print(f"  2. Run '{output_dir}/spx-start.sh' (macOS/Linux) or 'pwsh {output_dir}/spx-start.ps1' (Windows) to start the stack.")
            print(f"  3. Use '{output_dir}/spx-stop.sh' or 'pwsh {output_dir}/spx-stop.ps1' to shut everything down.")

            launch = input("\nStart the stack now? [Y/n]: ").strip().lower()
            if launch in {"", "y", "yes"}:
                _launch_stack(output_dir)
        return 0
    if args.command == "bootstrap":
        from .bootstrap import bootstrap

        bootstrap(Path(args.bundle), args.api_url)
        return 0
    raise ValueError(f"Unsupported command: {args.command}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return run(args)


def _launch_stack(output_dir: Path) -> None:
    if os.name == "nt":
        script = output_dir / "spx-start.ps1"
        if not script.exists():
            print(f"[spx-installer] Cannot find {script}; skipping start.")
            return
        shell = shutil.which("pwsh") or shutil.which("powershell")
        if not shell:
            print("[spx-installer] Neither pwsh nor powershell is available; please start manually.")
            return
        cmd = [shell, "-ExecutionPolicy", "Bypass", "-File", str(script)]
    else:
        script = output_dir / "spx-start.sh"
        if not script.exists():
            print(f"[spx-installer] Cannot find {script}; skipping start.")
            return
        cmd = [str(script)]

    print(f"[spx-installer] Launching stack via {script} ...")
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as exc:
        print(f"[spx-installer] Start script exited with {exc.returncode}. Please inspect the logs.")


if __name__ == "__main__":
    raise SystemExit(main())
