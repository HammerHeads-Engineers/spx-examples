# SPDX-License-Identifier: MIT
"""Tests for packaging helpers."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from installer.package_utils import materialize_industry_model_links


def _write_target(root: Path) -> Path:
    target = root / "library" / "domains" / "iot" / "generic" / "sensor.yaml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("name: sensor\nattributes: {}\n", encoding="utf-8")
    return target


def test_materialize_placeholder_link_file(tmp_path: Path) -> None:
    target = _write_target(tmp_path)
    placeholder = (
        tmp_path / "library" / "industries" / "pack_a" / "sensors" / "sensor.yaml"
    )
    placeholder.parent.mkdir(parents=True, exist_ok=True)
    placeholder.write_text(
        "../../../domains/iot/generic/sensor.yaml\n", encoding="utf-8"
    )

    count = materialize_industry_model_links(tmp_path)

    assert count == 1
    assert not placeholder.is_symlink()
    assert placeholder.read_text(encoding="utf-8") == target.read_text(encoding="utf-8")


def test_materialize_ignores_regular_yaml_files(tmp_path: Path) -> None:
    _write_target(tmp_path)
    regular = tmp_path / "library" / "industries" / "pack_a" / "README.yaml"
    regular.parent.mkdir(parents=True, exist_ok=True)
    regular.write_text("name: pack-a\n", encoding="utf-8")

    count = materialize_industry_model_links(tmp_path)

    assert count == 0
    assert regular.read_text(encoding="utf-8") == "name: pack-a\n"


def test_materialize_symlink_when_supported(tmp_path: Path) -> None:
    target = _write_target(tmp_path)
    link = tmp_path / "library" / "industries" / "pack_a" / "sensors" / "sensor.yaml"
    link.parent.mkdir(parents=True, exist_ok=True)

    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks not supported in this environment.")

    count = materialize_industry_model_links(tmp_path)

    assert count == 1
    assert not link.is_symlink()
    assert link.read_text(encoding="utf-8") == target.read_text(encoding="utf-8")
