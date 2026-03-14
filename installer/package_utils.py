# SPDX-License-Identifier: MIT
"""Packaging helpers for distributable installer artifacts."""

from __future__ import annotations

import argparse
from pathlib import Path


def _resolve_placeholder_target(path: Path) -> Path | None:
    if path.is_symlink():
        try:
            target = path.resolve(strict=True)
        except FileNotFoundError:
            return None
        return target if target.is_file() else None

    try:
        raw = path.read_text(encoding="utf-8").strip()
    except UnicodeDecodeError:
        return None

    normalized = raw.replace("\\", "/")
    if not normalized.startswith("../") or not normalized.endswith(".yaml"):
        return None
    if "\n" in raw or "\r" in raw:
        return None

    target = (path.parent / raw).resolve()
    return target if target.is_file() else None


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

    materialized = 0
    for path in industries_root.rglob("*.yaml"):
        target = _resolve_placeholder_target(path)
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
    count = materialize_industry_model_links(package_root)
    print(
        f"[package_utils] Materialized {count} industry model link(s) in {package_root}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
