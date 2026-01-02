#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Sync Home Assistant config from a generated bundle into installer assets."""

from __future__ import annotations

import argparse
import fnmatch
import os
import shutil
import sys
from pathlib import Path


RUNTIME_EXCLUDES = [
    "home-assistant.log*",
    "home-assistant_v2.db*",
    ".ha_run.lock",
]


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[1]
    default_src = repo_root / "build" / "spx-generated" / "assets" / "homeassistant" / "config"
    default_dest = repo_root / "library" / "assets" / "homeassistant" / "config"
    parser = argparse.ArgumentParser(
        description="Copy Home Assistant config into installer assets.",
    )
    parser.add_argument("--source", type=Path, default=default_src, help="Source HA config directory.")
    parser.add_argument("--dest", type=Path, default=default_dest, help="Destination assets directory.")
    parser.add_argument(
        "--include-runtime",
        action="store_true",
        help="Include runtime files (logs, db, lock).",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove destination contents before copying.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print actions without copying.",
    )
    return parser.parse_args()


def should_skip(name: str, *, include_runtime: bool) -> bool:
    if include_runtime:
        return False
    return any(fnmatch.fnmatch(name, pattern) for pattern in RUNTIME_EXCLUDES)


def clear_destination(dest: Path, *, dry_run: bool) -> None:
    if not dest.exists():
        return
    for entry in dest.iterdir():
        if dry_run:
            print(f"[sync-ha] remove {entry}")
            continue
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry)
        else:
            entry.unlink()


def copy_tree(source: Path, dest: Path, *, include_runtime: bool, dry_run: bool) -> None:
    for root, dirs, files in os.walk(source):
        root_path = Path(root)
        rel_root = root_path.relative_to(source)
        dest_root = dest / rel_root
        if not dry_run:
            dest_root.mkdir(parents=True, exist_ok=True)

        for name in files:
            if should_skip(name, include_runtime=include_runtime):
                continue
            src_path = root_path / name
            dest_path = dest_root / name
            if dry_run:
                print(f"[sync-ha] copy {src_path} -> {dest_path}")
            else:
                shutil.copy2(src_path, dest_path)


def main() -> int:
    args = parse_args()
    source = args.source
    dest = args.dest

    if not source.exists():
        print(f"[sync-ha] Source does not exist: {source}", file=sys.stderr)
        return 1
    if args.clean:
        clear_destination(dest, dry_run=args.dry_run)
    if not args.dry_run:
        dest.mkdir(parents=True, exist_ok=True)
    copy_tree(source, dest, include_runtime=args.include_runtime, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
