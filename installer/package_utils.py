# SPDX-License-Identifier: MIT
"""Packaging helpers for distributable installer artifacts."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path, PurePosixPath


class PackageMaterializationError(RuntimeError):
    """Raised when an industry model reference cannot be materialized safely."""


def _ensure_allowed_target(source: Path, target: Path, domains_root: Path) -> Path:
    try:
        resolved = target.resolve(strict=True)
    except FileNotFoundError as exc:
        raise PackageMaterializationError(
            f"{source} points to missing target {target}"
        ) from exc

    if not resolved.is_file():
        raise PackageMaterializationError(
            f"{source} points to non-file target {resolved}"
        )

    try:
        resolved.relative_to(domains_root)
    except ValueError as exc:
        raise PackageMaterializationError(
            f"{source} points outside {domains_root} (points to {resolved})"
        ) from exc

    return resolved


def _resolve_placeholder_target(path: Path, domains_root: Path) -> Path | None:
    if path.is_symlink():
        return _ensure_allowed_target(path, path.resolve(strict=False), domains_root)

    try:
        raw = path.read_text(encoding="utf-8").strip()
    except UnicodeDecodeError:
        return None

    normalized = raw.replace("\\", "/")
    if not normalized.startswith("../") or not normalized.endswith(".yaml"):
        return None
    if "\n" in raw or "\r" in raw:
        return None

    target = path.parent / Path(*PurePosixPath(normalized).parts)
    return _ensure_allowed_target(path, target, domains_root)


def materialize_industry_model_links(package_root: Path) -> int:
    """Replace industry model links/placeholders with concrete YAML files.

    Git stores `library/industries/**/*.yaml` as symlinks into `library/domains`.
    Windows checkouts with `core.symlinks=false` turn them into tiny text files
    containing the relative target path. Distributable packages should carry the
    concrete model YAML instead so extraction does not depend on symlink support.
    """

    industries_root = package_root / "library" / "industries"
    if not industries_root.exists():
        return 0

    domains_root = (package_root / "library" / "domains").resolve()
    materialized = 0
    for path in industries_root.rglob("*.yaml"):
        target = _resolve_placeholder_target(path, domains_root)
        if target is None:
            continue

        payload = target.read_bytes()
        if path.is_symlink():
            path.unlink()
        path.write_bytes(payload)
        materialized += 1

    return materialized


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m installer.package_utils",
        description="Materialize pack model links/placeholders inside a package directory.",
    )
    parser.add_argument("package_root", help="Path to the assembled package directory.")
    args = parser.parse_args(argv)

    package_root = Path(args.package_root).resolve()
    try:
        count = materialize_industry_model_links(package_root)
    except PackageMaterializationError as exc:
        print(f"[package_utils] {exc}", file=sys.stderr)
        return 1
    print(
        f"[package_utils] Materialized {count} industry model link(s) in {package_root}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
