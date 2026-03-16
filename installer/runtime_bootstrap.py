#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Create or reuse a local virtualenv and print its Python interpreter path."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare a local Python runtime for the SPX installer."
    )
    parser.add_argument(
        "--venv-dir",
        required=True,
        help="Directory where the virtual environment should live.",
    )
    parser.add_argument(
        "--package",
        action="append",
        default=[],
        help="Package requirement to install into the virtual environment.",
    )
    return parser.parse_args(argv)


def venv_python_path(venv_dir: Path) -> Path:
    if sys.platform == "win32":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def read_stamp(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except json.JSONDecodeError:
        return None


def write_stamp(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def run_command(argv: list[str]) -> None:
    subprocess.run(argv, check=True, stdout=sys.stderr, stderr=sys.stderr)


def normalize_packages(packages: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for package in packages:
        item = package.strip()
        if not item or item in seen:
            continue
        seen.add(item)
        normalized.append(item)
    return normalized


def ensure_runtime(venv_dir: Path, packages: list[str]) -> Path:
    venv_dir.mkdir(parents=True, exist_ok=True)
    python_bin = venv_python_path(venv_dir)
    stamp_path = venv_dir / ".spx-runtime.json"
    desired_state = {
        "packages": packages,
        "python_version": sys.version,
    }

    if not python_bin.exists():
        print(
            f"[runtime] Creating Python virtual environment at {venv_dir}",
            file=sys.stderr,
        )
        run_command([sys.executable, "-m", "venv", str(venv_dir)])

    current_state = read_stamp(stamp_path)
    if current_state != desired_state:
        if packages:
            print(
                f"[runtime] Installing Python packages into {venv_dir}",
                file=sys.stderr,
            )
            run_command(
                [
                    str(python_bin),
                    "-m",
                    "pip",
                    "install",
                    "--disable-pip-version-check",
                    *packages,
                ]
            )
        write_stamp(stamp_path, desired_state)

    return python_bin


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    packages = normalize_packages(args.package)
    python_bin = ensure_runtime(Path(args.venv_dir).expanduser().resolve(), packages)
    print(str(python_bin))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
