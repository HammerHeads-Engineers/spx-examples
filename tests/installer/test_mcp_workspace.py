# SPDX-License-Identifier: MIT
"""Tests for the installer-managed Codex MCP workspace bootstrap."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from installer import mcp_workspace


def test_default_workspace_dir_uses_documents_on_macos(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()

    result = mcp_workspace.default_workspace_dir(home=home, platform_name="darwin")

    assert result == home / "Documents" / "SPX Codex Workspace"


def test_default_workspace_dir_uses_local_app_data_on_windows(
    tmp_path: Path,
    monkeypatch,
) -> None:
    home = tmp_path / "home"
    local_app_data = home / "AppData" / "Local"
    local_app_data.mkdir(parents=True)
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))

    result = mcp_workspace.default_workspace_dir(home=home, platform_name="win32")

    assert result == local_app_data / "SPX" / "workspace"


def test_build_workspace_env_prefers_seed_and_defaults() -> None:
    values = mcp_workspace.build_workspace_env(
        existing={"CUSTOM_FLAG": "1"},
        seeded={
            "SPX_PRODUCT_KEY": "REAL-KEY",
            "SPX_BASE_URL": "http://localhost:8000/",
        },
    )

    assert values["SPX_PRODUCT_KEY"] == "REAL-KEY"
    assert values["SPX_BASE_URL"] == "http://localhost:8000"
    assert values["CUSTOM_FLAG"] == "1"


def test_build_workspace_env_preserves_existing_base_url_when_seed_missing() -> None:
    values = mcp_workspace.build_workspace_env(
        existing={"SPX_BASE_URL": "http://custom-host:8000/", "SPX_PRODUCT_KEY": "KEEP"},
        seeded={},
    )

    assert values["SPX_BASE_URL"] == "http://custom-host:8000"
    assert values["SPX_PRODUCT_KEY"] == "KEEP"


def test_sync_payload_replaces_managed_entries_and_keeps_local_state(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    (source_root / "README.md").write_text("new readme\n", encoding="utf-8")
    docs_dir = source_root / "docs"
    docs_dir.mkdir()
    (docs_dir / "MCP.md").write_text("docs\n", encoding="utf-8")
    (source_root / "junk.txt").write_text("do not copy\n", encoding="utf-8")

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "README.md").write_text("old readme\n", encoding="utf-8")
    venv_dir = workspace / ".venv"
    venv_dir.mkdir()
    codex_dir = workspace / ".codex"
    codex_dir.mkdir()
    (workspace / "local.txt").write_text("keep me\n", encoding="utf-8")

    mcp_workspace.sync_payload(source_root, workspace)

    assert (workspace / "README.md").read_text(encoding="utf-8") == "new readme\n"
    assert (workspace / "docs" / "MCP.md").read_text(encoding="utf-8") == "docs\n"
    assert not (workspace / "junk.txt").exists()
    assert venv_dir.exists()
    assert codex_dir.exists()
    assert (workspace / "local.txt").read_text(encoding="utf-8") == "keep me\n"


def test_sync_payload_skips_unreadable_files(tmp_path: Path, monkeypatch, capsys) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    library_dir = source_root / "library" / "assets" / "matter" / "data"
    library_dir.mkdir(parents=True)
    readable_file = library_dir / "chip.json"
    blocked_file = library_dir / "chip_config.ini"
    readable_file.write_text('{"ok": true}\n', encoding="utf-8")
    blocked_file.write_text("secret\n", encoding="utf-8")

    original_copy2 = mcp_workspace.shutil.copy2

    def flaky_copy2(src, dest, *args, **kwargs):
        if Path(src).name == blocked_file.name:
            raise PermissionError("permission denied")
        return original_copy2(src, dest, *args, **kwargs)

    monkeypatch.setattr(mcp_workspace.shutil, "copy2", flaky_copy2)

    workspace = tmp_path / "workspace"
    workspace.mkdir()

    mcp_workspace.sync_payload(source_root, workspace)

    assert (workspace / "library" / "assets" / "matter" / "data" / "chip.json").exists()
    assert not (workspace / "library" / "assets" / "matter" / "data" / "chip_config.ini").exists()
    stderr = capsys.readouterr().err
    assert "Skipping unreadable payload file" in stderr
    assert str(blocked_file) in stderr


def test_bootstrap_runtime_installs_workspace_editably(tmp_path: Path, monkeypatch) -> None:
    source_root = tmp_path / "source"
    runtime_helper = source_root / "installer" / "runtime_bootstrap.py"
    runtime_helper.parent.mkdir(parents=True)
    runtime_helper.write_text("", encoding="utf-8")
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    calls: list[list[str]] = []
    expected_python = workspace / ".venv" / "bin" / "python"

    def fake_run(argv, *, cwd=None, capture_output=False):
        calls.append(argv)
        if "runtime_bootstrap.py" in argv[1]:
            return SimpleNamespace(stdout=str(expected_python) + "\n")
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(mcp_workspace, "run_command", fake_run)

    result = mcp_workspace.bootstrap_runtime(source_root, workspace, "python3.11")

    assert result == expected_python
    assert calls[0] == [
        "python3.11",
        str(runtime_helper),
        "--venv-dir",
        str(workspace / ".venv"),
    ]
    assert calls[1] == [
        str(expected_python),
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "-e",
        str(workspace),
    ]


def test_bootstrap_codex_uses_read_only_by_default(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    tools_dir = workspace / "tools"
    tools_dir.mkdir(parents=True)
    (tools_dir / "codex_mcp_bootstrap.py").write_text("", encoding="utf-8")
    calls: list[list[str]] = []

    def fake_run(argv, *, cwd=None, capture_output=False):
        calls.append(argv)
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(mcp_workspace, "run_command", fake_run)

    mcp_workspace.bootstrap_codex(
        workspace,
        "python3.11",
        server_name="spx",
        allow_write=False,
    )

    assert calls == [[
        "python3.11",
        str(workspace / "tools" / "codex_mcp_bootstrap.py"),
        "--repo-root",
        str(workspace),
        "--server-name",
        "spx",
        "--skip-git-exclude",
        "--read-only",
    ]]
