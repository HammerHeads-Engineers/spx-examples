# SPDX-License-Identifier: MIT
"""Helper utilities for resolving manifest locations."""

from __future__ import annotations

from pathlib import Path


def repo_root() -> Path:
    """Return repository root assumed to be two levels up from this file."""
    return Path(__file__).resolve().parents[1]


def catalog_dir() -> Path:
    """Return the path to the catalog directory."""
    return repo_root() / "library" / "catalog"


def profiles_dir() -> Path:
    """Return the path to the profiles directory."""
    return repo_root() / "profiles"

