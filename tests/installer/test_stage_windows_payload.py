# SPDX-License-Identifier: MIT

import json
from pathlib import Path

from tools.stage_windows_payload import (
    MAX_WIX_ID_LENGTH,
    make_id,
    render_wix_fragment,
    stage_payload,
    write_manifest,
)


def test_stage_payload_copies_known_entries_and_extra_overlay(tmp_path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "installer").mkdir(parents=True)
    (repo_root / "installer" / "__init__.py").write_text("", encoding="utf-8")
    (repo_root / "library" / "catalog").mkdir(parents=True)
    (repo_root / "library" / "catalog" / "models.yaml").write_text("models: []\n", encoding="utf-8")
    (repo_root / "README.md").write_text("readme\n", encoding="utf-8")
    (repo_root / "LICENSE").write_text("license\n", encoding="utf-8")
    (repo_root / "spx-install.ps1").write_text("Write-Host 'ok'\n", encoding="utf-8")

    publish_dir = tmp_path / "publish"
    publish_dir.mkdir()
    (publish_dir / "SpxLauncher.exe").write_bytes(b"launcher")

    output_dir = tmp_path / "stage"
    staged_entries = stage_payload(repo_root, output_dir, extra_paths=[publish_dir])

    assert "installer" in staged_entries
    assert "library" in staged_entries
    assert (output_dir / "installer" / "__init__.py").exists()
    assert (output_dir / "library" / "catalog" / "models.yaml").exists()
    assert (output_dir / "SpxLauncher.exe").read_bytes() == b"launcher"


def test_render_wix_fragment_adds_launcher_shortcuts_and_subdirectories(tmp_path) -> None:
    stage_dir = tmp_path / "stage"
    (stage_dir / "installer").mkdir(parents=True)
    (stage_dir / "installer" / "runner.py").write_text("print('ok')\n", encoding="utf-8")
    (stage_dir / "SpxLauncher.exe").write_bytes(b"launcher")

    fragment = render_wix_fragment(stage_dir)

    assert 'ComponentGroup Id="PayloadComponents" Directory="INSTALLFOLDER"' in fragment
    assert 'File Id="filSpxLauncherExe"' in fragment
    assert 'Shortcut Id="shortcutSpxSetup"' in fragment
    assert 'Arguments="setup --pause-on-error"' in fragment
    assert 'Arguments="mcp-setup --pause-on-error"' in fragment
    assert 'Subdirectory="installer"' in fragment


def test_write_manifest_lists_relative_files_sorted(tmp_path) -> None:
    stage_dir = tmp_path / "stage"
    (stage_dir / "profiles").mkdir(parents=True)
    (stage_dir / "profiles" / "default.yaml").write_text("name: default\n", encoding="utf-8")
    (stage_dir / "README.md").write_text("readme\n", encoding="utf-8")

    manifest_path = tmp_path / "payload-manifest.json"
    write_manifest(manifest_path, staged_entries=["profiles", "README.md"], stage_dir=stage_dir)

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["staged_entries"] == ["profiles", "README.md"]
    assert payload["files"] == ["README.md", "profiles/default.yaml"]


def test_make_id_caps_wix_identifier_length() -> None:
    relative_path = Path("library") / ("very_long_segment_" * 8) / "model.yaml"
    wix_id = make_id("cmp", relative_path)

    assert len(wix_id) <= MAX_WIX_ID_LENGTH
