# SPDX-License-Identifier: MIT
"""Helpers for locating the repository root in tests."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def repo_root() -> Path:
    """Return the repository root path.

    Assumes this file lives in `<repo>/tests/common/`.
    """

    return Path(__file__).resolve().parents[2]
