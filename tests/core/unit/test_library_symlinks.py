# SPDX-License-Identifier: MIT
"""Validate that industry model refs point back into library/domains."""

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


def _resolve_industry_model_target(path: Path) -> Path:
    if path.is_symlink():
        return path.resolve()

    raw = path.read_text(encoding="utf-8").strip()
    normalized = raw.replace("\\", "/")
    if (
        normalized.startswith("../")
        and normalized.endswith(".yaml")
        and "\n" not in raw
        and "\r" not in raw
    ):
        return (path.parent / raw).resolve()

    pytest.fail(
        f"{path} is neither a symlink nor a relative placeholder reference into library/domains"
    )


@pytest.mark.parametrize("path", _iter_industry_model_files())
def test_industry_models_reference_domain_models(path: Path) -> None:
    target = _resolve_industry_model_target(path)
    assert target.exists(), f"{path} points to missing target {target}"
    domains_root = (ROOT / "library" / "domains").resolve()
    assert (
        domains_root in target.parents
    ), f"{path} points outside library/domains (points to {target})"
