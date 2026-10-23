#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Create or reuse a local virtualenv and print its Python interpreter path."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any


PIP_BOOTSTRAP = (
    "pip @ https://files.pythonhosted.org/packages/3f/06/"
    "3e4420302363fbb71be3c7f35ce042f54bfca330e3e66b3a2e3c4cca579f/"
    "pip-26.2.2-py3-none-any.whl#sha256="
    "fd7f4dfa8190e014013b9f08f3e973f4e4c26ffd179a204895533a7254813a70"
)
SECURITY_MINIMUMS = {"pip": "26.2.2", "certifi": "2026.10.19", "uv": "0.13.4"}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare a local Python runtime for the SPX installer."
    )
    parser.add_argument(
        "--venv-dir",
        help="Directory where the virtual environment should live.",
    )
    parser.add_argument(
        "--secure-only",
        action="store_true",
        help="Secure this interpreter without creating a venv.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify this interpreter without changing it.",
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
    environment = os.environ.copy()
    # GUI launchers can inherit an inaccessible TLS keylog path. Package
    # installation needs verified HTTPS, not the launcher's TLS diagnostics.
    environment.pop("SSLKEYLOGFILE", None)
    subprocess.run(
        argv, check=True, stdout=sys.stderr, stderr=sys.stderr, env=environment
    )


def has_module(python_bin: Path, module_name: str) -> bool:
    try:
        subprocess.run(
            [
                str(python_bin),
                "-c",
                (
                    "import importlib.util, sys; "
                    f"sys.exit(0 if importlib.util.find_spec({module_name!r}) else 1)"
                ),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False
    return True


def environment_versions(python_bin: Path) -> dict[str, Any]:
    result = subprocess.run(
        [
            str(python_bin),
            "-c",
            "import json, sys; from importlib import metadata; "
            "names = ('pip', 'certifi', 'uv'); "
            "installed = {d.metadata['Name'].lower(): d.version for d in metadata.distributions() "
            "if d.metadata.get('Name', '').lower() in names}; "
            "print(json.dumps(dict(installed, python=list(sys.version_info[:3]))))",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def safe_version(version: str | None, minimum: str) -> bool:
    # Prereleases and unknown vendor versions must not pass the security gate.
    if version is None or not re.fullmatch(r"\d+(?:\.\d+)*", version):
        return False
    parts = tuple(int(part) for part in version.split("."))
    floor = tuple(int(part) for part in minimum.split("."))
    width = max(len(parts), len(floor))
    return parts + (0,) * (width - len(parts)) >= floor + (0,) * (width - len(floor))


def ensure_pip_available(python_bin: Path) -> None:
    versions = environment_versions(python_bin)
    if tuple(versions["python"][:2]) < (3, 10):
        raise RuntimeError(
            "Secure SPX package installation requires Python 3.10+. "
            "Migrate this environment; the advisory bootstrap does not support Python 3.9."
        )
    if safe_version(versions.get("pip"), SECURITY_MINIMUMS["pip"]):
        return
    if not has_module(python_bin, "pip"):
        # ensurepip is offline and only seeds the installer; it is not remediation.
        run_command([str(python_bin), "-m", "ensurepip", "--upgrade"])
    run_command(
        [
            str(python_bin),
            "-m",
            "pip",
            "--disable-pip-version-check",
            "install",
            "--no-index",
            "--no-deps",
            PIP_BOOTSTRAP,
        ]
    )
    if not safe_version(
        environment_versions(python_bin).get("pip"), SECURITY_MINIMUMS["pip"]
    ):
        raise RuntimeError("Pinned pip bootstrap did not produce a safe pip version.")


def ensure_secure_environment(python_bin: Path) -> None:
    ensure_pip_available(python_bin)
    versions = environment_versions(python_bin)
    requirements = [
        f"{name}>={minimum}"
        for name, minimum in SECURITY_MINIMUMS.items()
        if name != "pip"
        and (name == "certifi" or name in versions)
        and not safe_version(versions.get(name), minimum)
    ]
    if requirements:
        run_command(
            [
                str(python_bin),
                "-m",
                "pip",
                "--disable-pip-version-check",
                "install",
                "--upgrade",
                *requirements,
            ]
        )
    verify_environment(python_bin)


def verify_environment(python_bin: Path) -> dict[str, Any]:
    versions = environment_versions(python_bin)
    for name, minimum in SECURITY_MINIMUMS.items():
        if name == "uv" and name not in versions:
            continue
        if not safe_version(versions.get(name), minimum):
            raise RuntimeError(
                f"Unsafe {name} in {python_bin}: {versions.get(name)!r}; require >= {minimum}"
            )
    return versions


def is_healthy_virtualenv(venv_dir: Path) -> bool:
    python_bin = venv_python_path(venv_dir)
    if not python_bin.exists():
        return False
    if not (venv_dir / "pyvenv.cfg").exists():
        return False

    try:
        subprocess.run(
            [
                str(python_bin),
                "-c",
                (
                    "import pathlib, sys; "
                    "prefix = pathlib.Path(sys.prefix); "
                    "raise SystemExit(0 if sys.prefix != sys.base_prefix and "
                    "prefix.joinpath('pyvenv.cfg').exists() else 1)"
                ),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False

    return True


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
        "python_executable": str(Path(sys.executable).resolve()),
        "python_version": sys.version,
    }

    if not is_healthy_virtualenv(venv_dir):
        if any(venv_dir.iterdir()):
            print(
                f"[runtime] Recreating broken Python virtual environment at {venv_dir}",
                file=sys.stderr,
            )
            shutil.rmtree(venv_dir)
            venv_dir.mkdir(parents=True, exist_ok=True)
        print(
            f"[runtime] Creating Python virtual environment at {venv_dir}",
            file=sys.stderr,
        )
        run_command([sys.executable, "-m", "venv", str(venv_dir)])
        python_bin = venv_python_path(venv_dir)
    # Security is independent of the package/cache stamp, including empty runtimes.
    ensure_secure_environment(python_bin)
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
                    "certifi>=2026.10.19",
                    *packages,
                ]
            )
        ensure_secure_environment(python_bin)
        write_stamp(stamp_path, desired_state)

    return python_bin


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.check:
        print(json.dumps(verify_environment(Path(sys.executable)), sort_keys=True))
        return 0
    if args.secure_only:
        ensure_secure_environment(Path(sys.executable))
        return 0
    if not args.venv_dir:
        raise SystemExit("--venv-dir, --secure-only or --check is required")
    packages = normalize_packages(args.package)
    python_bin = ensure_runtime(Path(args.venv_dir).expanduser().resolve(), packages)
    print(str(python_bin))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
