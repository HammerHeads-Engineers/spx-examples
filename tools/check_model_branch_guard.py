#!/usr/bin/env python3
"""Guard rails for model-yaml automation branch drift and duplicate additions.

This script is designed to prevent the automation/model-yaml branch from
re-adding models that already exist on develop and from modifying existing
models without explicit override.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import os
import subprocess
import sys
from typing import Iterable

import yaml


CATALOG_PATH = Path("library/catalog/models.yaml")
MODEL_ROOT_PREFIX = "library/domains/"
AUTOMATION_BRANCH = "automation/model-yaml"


@dataclass(frozen=True)
class CatalogEntry:
    entry_id: str
    path: str


@dataclass(frozen=True)
class ChangedFile:
    status: str
    path: str
    old_path: str | None = None


def _run_git(root: Path, args: list[str], check: bool = True) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=root,
        text=True,
        capture_output=True,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed with exit {proc.returncode}: {proc.stderr.strip()}"
        )
    return proc.stdout


def _is_shallow_repository(root: Path) -> bool:
    out = _run_git(root, ["rev-parse", "--is-shallow-repository"], check=False).strip().lower()
    return out == "true"


def _ensure_base_ref(root: Path, base_ref: str) -> None:
    verify = subprocess.run(
        ["git", "rev-parse", "--verify", base_ref],
        cwd=root,
        text=True,
        capture_output=True,
    )
    if verify.returncode == 0:
        return

    if base_ref.startswith("origin/") and "/" in base_ref:
        remote, branch = base_ref.split("/", 1)
        fetch = subprocess.run(
            ["git", "fetch", remote, branch],
            cwd=root,
            text=True,
            capture_output=True,
        )
        if fetch.returncode != 0:
            raise RuntimeError(
                f"Unable to fetch {base_ref}: {fetch.stderr.strip()}"
            )

    verify2 = subprocess.run(
        ["git", "rev-parse", "--verify", base_ref],
        cwd=root,
        text=True,
        capture_output=True,
    )
    if verify2.returncode != 0:
        raise RuntimeError(
            f"Base ref {base_ref!r} is not available locally. Run: git fetch origin develop"
        )


def _changed_name_status(root: Path, base_ref: str) -> str:
    range_expr = f"{base_ref}...HEAD"
    try:
        return _run_git(root, ["diff", "--name-status", range_expr])
    except RuntimeError as exc:
        message = str(exc).lower()
        if "no merge base" not in message:
            raise

        # CI runners may have shallow history and miss the merge base even for valid refs.
        if _is_shallow_repository(root):
            subprocess.run(
                ["git", "fetch", "--unshallow", "origin"],
                cwd=root,
                text=True,
                capture_output=True,
            )
            try:
                return _run_git(root, ["diff", "--name-status", range_expr])
            except RuntimeError as retry_exc:
                if "no merge base" not in str(retry_exc).lower():
                    raise

        print(
            "Model branch guard warning: no merge base for "
            f"{range_expr}; falling back to two-dot diff ({base_ref}..HEAD).",
            file=sys.stderr,
        )
        return _run_git(root, ["diff", "--name-status", f"{base_ref}..HEAD"])


def _load_catalog_from_worktree(root: Path) -> object:
    path = root / CATALOG_PATH
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _load_catalog_from_ref(root: Path, ref: str) -> object:
    payload = _run_git(root, ["show", f"{ref}:{CATALOG_PATH.as_posix()}"])
    return yaml.safe_load(payload)


def _parse_catalog_entries(doc: object) -> list[CatalogEntry]:
    if not isinstance(doc, dict):
        return []
    models = doc.get("models")
    if not isinstance(models, list):
        return []

    entries: list[CatalogEntry] = []
    for item in models:
        if not isinstance(item, dict):
            continue
        entry_id = item.get("id")
        path = item.get("path")
        if isinstance(entry_id, str) and entry_id and isinstance(path, str) and path:
            entries.append(CatalogEntry(entry_id=entry_id, path=path))
    return entries


def _count_by_attr(entries: Iterable[CatalogEntry], attr: str) -> Counter[str]:
    counter: Counter[str] = Counter()
    for entry in entries:
        value = getattr(entry, attr)
        if value:
            counter[value] += 1
    return counter


def duplicate_regressions(
    current_entries: list[CatalogEntry], base_entries: list[CatalogEntry]
) -> list[str]:
    errors: list[str] = []

    for attr, label in (("entry_id", "id"), ("path", "path")):
        current_counts = _count_by_attr(current_entries, attr)
        base_counts = _count_by_attr(base_entries, attr)
        keys = sorted(set(current_counts) | set(base_counts))
        for key in keys:
            curr = current_counts.get(key, 0)
            base = base_counts.get(key, 0)
            if curr > 1 and curr > base:
                errors.append(
                    f"catalog duplicate regression for {label} '{key}': current={curr}, base={base}"
                )

    return errors


def parse_name_status_lines(raw: str) -> list[ChangedFile]:
    changed: list[ChangedFile] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status = parts[0]

        if status.startswith(("R", "C")):
            if len(parts) >= 3:
                changed.append(ChangedFile(status=status[0], old_path=parts[1], path=parts[2]))
            continue

        if len(parts) >= 2:
            changed.append(ChangedFile(status=status[0], old_path=None, path=parts[1]))

    return changed


def _is_model_yaml(path: str) -> bool:
    return path.startswith(MODEL_ROOT_PREFIX) and path.endswith(".yaml")


def detect_branch_name(root: Path) -> str:
    env_branch = os.environ.get("GITHUB_HEAD_REF") or os.environ.get("GITHUB_REF_NAME")
    if env_branch:
        return env_branch
    return _run_git(root, ["rev-parse", "--abbrev-ref", "HEAD"]).strip()


def _load_base_model_paths(root: Path, base_ref: str) -> set[str]:
    listing = _run_git(root, ["ls-tree", "-r", "--name-only", base_ref, "library/domains"])
    return {line.strip() for line in listing.splitlines() if line.strip().endswith(".yaml")}


def existing_model_edit_violations(
    changed_files: list[ChangedFile],
    base_model_paths: set[str],
    strict_mode: bool,
    allow_existing_model_edits: bool,
) -> list[str]:
    if not strict_mode or allow_existing_model_edits:
        return []

    errors: list[str] = []
    for item in changed_files:
        if not _is_model_yaml(item.path):
            continue

        if item.status != "A":
            errors.append(
                "automation branch modifies an existing model file without override: "
                f"{item.path} (status {item.status})"
            )
            continue

        if item.path in base_model_paths:
            errors.append(
                "automation branch re-adds a model file already present on base ref: "
                f"{item.path}"
            )

    return errors


def added_model_stem_collisions(
    changed_files: list[ChangedFile], base_model_paths: set[str]
) -> list[str]:
    errors: list[str] = []
    base_stems = {
        Path(path).stem: path
        for path in sorted(base_model_paths)
        if path.startswith(MODEL_ROOT_PREFIX)
    }

    for item in changed_files:
        if item.status != "A" or not _is_model_yaml(item.path):
            continue
        stem = Path(item.path).stem
        existing_path = base_stems.get(stem)
        if existing_path and existing_path != item.path:
            errors.append(
                "added model file has the same stem as an existing base model: "
                f"{item.path} vs {existing_path}"
            )

    return errors


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Guard model-yaml branch against duplicate/replay model additions."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root (default: project root)",
    )
    parser.add_argument(
        "--base-ref",
        default="origin/develop",
        help="Git base ref used for dedupe/reconciler checks (default: origin/develop)",
    )
    parser.add_argument(
        "--force-strict",
        action="store_true",
        help="Enable strict automation checks regardless of current branch name.",
    )
    parser.add_argument(
        "--allow-existing-model-edits",
        action="store_true",
        help="Allow modifications of existing model files (use only for intentional maintenance).",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    root = args.root.resolve()

    try:
        _ensure_base_ref(root, args.base_ref)

        current_catalog = _load_catalog_from_worktree(root)
        base_catalog = _load_catalog_from_ref(root, args.base_ref)
        current_entries = _parse_catalog_entries(current_catalog)
        base_entries = _parse_catalog_entries(base_catalog)

        changed_raw = _changed_name_status(root, args.base_ref)
        changed_files = parse_name_status_lines(changed_raw)

        branch_name = detect_branch_name(root)
        strict_mode = args.force_strict or branch_name == AUTOMATION_BRANCH
        allow_existing_model_edits = (
            args.allow_existing_model_edits
            or _truthy_env("SPX_ALLOW_EXISTING_MODEL_EDITS")
        )

        base_model_paths = _load_base_model_paths(root, args.base_ref)

        errors: list[str] = []
        errors.extend(duplicate_regressions(current_entries, base_entries))
        errors.extend(
            existing_model_edit_violations(
                changed_files,
                base_model_paths,
                strict_mode=strict_mode,
                allow_existing_model_edits=allow_existing_model_edits,
            )
        )
        errors.extend(added_model_stem_collisions(changed_files, base_model_paths))

    except Exception as exc:
        print(f"Model branch guard failed: {exc}")
        return 1

    if errors:
        print("Model branch guard failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(
        "Model branch guard passed "
        f"(base={args.base_ref}, branch={branch_name}, strict={'on' if strict_mode else 'off'})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
