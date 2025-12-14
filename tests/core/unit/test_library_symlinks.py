# SPDX-License-Identifier: MIT
"""Validate that industry model files are symbolic links into library/domains."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.common.repo import repo_root

ROOT = repo_root()


def _iter_industry_model_files() -> list[Path]:
    industries_root = ROOT / "library" / "industries"
    files = []
    for path in industries_root.rglob("*.yaml"):
        # Skip manifest files such as industries/config README files
        if path.name in {"README.md"}:
            continue
        files.append(path)
    return files


@pytest.mark.parametrize("path", _iter_industry_model_files())
def test_industry_models_are_symlinks(path: Path) -> None:
    assert path.is_symlink(), f"{path} is not a symlink; models must live in library/domains"
    target = path.resolve()
    domains_root = (ROOT / "library" / "domains").resolve()
    assert domains_root in target.parents, f"{path} links outside library/domains (points to {target})"
