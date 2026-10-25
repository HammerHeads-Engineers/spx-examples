# SPDX-License-Identifier: MIT

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_guard_module():
    root = Path(__file__).resolve().parents[3]
    script_path = root / "tools" / "check_model_branch_guard.py"
    spec = importlib.util.spec_from_file_location(
        "check_model_branch_guard", script_path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_parse_name_status_lines_supports_add_modify_and_rename() -> None:
    guard = _load_guard_module()

    raw = "\n".join(
        [
            "A\tlibrary/domains/energy/meter/vendor/new_meter__modbus.yaml",
            "M\tlibrary/catalog/models.yaml",
            "R100\told.yaml\tnew.yaml",
        ]
    )

    parsed = guard.parse_name_status_lines(raw)

    assert len(parsed) == 3
    assert parsed[0].status == "A"
    assert parsed[0].path.endswith("new_meter__modbus.yaml")
    assert parsed[1].status == "M"
    assert parsed[1].path == "library/catalog/models.yaml"
    assert parsed[2].status == "R"
    assert parsed[2].old_path == "old.yaml"
    assert parsed[2].path == "new.yaml"


def test_duplicate_regressions_detects_count_increase_vs_base() -> None:
    guard = _load_guard_module()

    base_entries = [
        guard.CatalogEntry(entry_id="Energy.Em24.Modbus", path="a.yaml"),
        guard.CatalogEntry(entry_id="Energy.Em24.Modbus", path="a.yaml"),
    ]
    current_entries = [
        guard.CatalogEntry(entry_id="Energy.Em24.Modbus", path="a.yaml"),
        guard.CatalogEntry(entry_id="Energy.Em24.Modbus", path="a.yaml"),
        guard.CatalogEntry(entry_id="Energy.Em24.Modbus", path="a.yaml"),
    ]

    errors = guard.duplicate_regressions(current_entries, base_entries)

    assert errors
    assert any("duplicate regression" in err for err in errors)


def test_existing_model_edit_violations_blocks_modification_in_strict_mode() -> None:
    guard = _load_guard_module()

    changed = [
        guard.ChangedFile(
            status="M",
            path="library/domains/energy/meter/socomec/diris_a40__modbus.yaml",
            old_path=None,
        )
    ]

    errors = guard.existing_model_edit_violations(
        changed,
        base_model_paths={
            "library/domains/energy/meter/socomec/diris_a40__modbus.yaml"
        },
        strict_mode=True,
        allow_existing_model_edits=False,
    )

    assert errors
    assert "modifies an existing model file" in errors[0]


def test_changed_name_status_falls_back_when_no_merge_base(monkeypatch, capsys) -> None:
    guard = _load_guard_module()
    calls: list[list[str]] = []

    def fake_run_git(root, args, check=True):
        calls.append(args)
        if args == ["diff", "--name-status", "origin/develop...HEAD"]:
            raise RuntimeError(
                "git diff --name-status origin/develop...HEAD failed: no merge base"
            )
        if args == ["diff", "--name-status", "origin/develop..HEAD"]:
            return "A\tlibrary/domains/energy/meter/vendor/new_meter__modbus.yaml\n"
        return ""

    monkeypatch.setattr(guard, "_run_git", fake_run_git)
    monkeypatch.setattr(guard, "_is_shallow_repository", lambda root: False)

    output = guard._changed_name_status(Path("."), "origin/develop")

    assert output.startswith("A\tlibrary/domains/")
    assert ["diff", "--name-status", "origin/develop...HEAD"] in calls
    assert ["diff", "--name-status", "origin/develop..HEAD"] in calls
    assert "falling back to two-dot diff" in capsys.readouterr().err
