# SPDX-License-Identifier: MIT
"""Tests for the installer-managed Codex MCP workspace bootstrap."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from installer import mcp_workspace


def build_minimal_workspace_source(root: Path) -> Path:
    (root / "spx_mcp").mkdir(parents=True)
    (root / "spx_mcp" / "__init__.py").write_text("", encoding="utf-8")
    (root / "tools").mkdir(parents=True)
    (root / "tools" / "codex_mcp_bootstrap.py").write_text("", encoding="utf-8")
    (root / "installer").mkdir(parents=True)
    (root / "installer" / "runtime_bootstrap.py").write_text("", encoding="utf-8")
    catalog_dir = root / "library" / "catalog"
    catalog_dir.mkdir(parents=True)
    (catalog_dir / "models.yaml").write_text("models: []\n", encoding="utf-8")
    (root / "pyproject.toml").write_text("[tool.poetry]\nname='spx-examples'\n", encoding="utf-8")
    (root / "README.md").write_text("workspace\n", encoding="utf-8")
    (root / "AGENTS.md").write_text("agents\n", encoding="utf-8")
    (root / "docs").mkdir(parents=True)
    (root / "docs" / "MCP.md").write_text("mcp\n", encoding="utf-8")
    return root


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
            "SPX_PRODUCT_KEY": "TEST-PRODUCT-KEY",
            "SPX_BASE_URL": "http://localhost:8000/",
        },
    )

    assert values["SPX_PRODUCT_KEY"] == "TEST-PRODUCT-KEY"
    assert values["SPX_BASE_URL"] == "http://localhost:8000"
    assert values["CUSTOM_FLAG"] == "1"


def test_build_workspace_env_preserves_existing_base_url_when_seed_missing() -> None:
    values = mcp_workspace.build_workspace_env(
        existing={"SPX_BASE_URL": "http://custom-host:8000/", "SPX_PRODUCT_KEY": "KEEP"},
        seeded={},
    )

    assert values["SPX_BASE_URL"] == "http://custom-host:8000"
    assert values["SPX_PRODUCT_KEY"] == "KEEP"


def test_build_workspace_env_treats_placeholder_as_missing() -> None:
    values = mcp_workspace.build_workspace_env(
        existing={"SPX_PRODUCT_KEY": "REPLACE_ME"},
        seeded={"SPX_PRODUCT_KEY": "TEST-PRODUCT-KEY"},
    )

    assert values["SPX_PRODUCT_KEY"] == "TEST-PRODUCT-KEY"


def test_resolve_allow_write_defaults_to_true() -> None:
    assert mcp_workspace.resolve_allow_write(None) is True
    assert mcp_workspace.resolve_allow_write(True) is True
    assert mcp_workspace.resolve_allow_write(False) is False


def test_read_seeded_workspace_env_falls_back_to_source_env_when_primary_has_placeholder(
    tmp_path: Path,
) -> None:
    primary_env = tmp_path / "primary.env"
    fallback_env = tmp_path / "fallback.env"
    primary_env.write_text("SPX_PRODUCT_KEY=REPLACE_ME\n", encoding="utf-8")
    fallback_env.write_text(
        "SPX_PRODUCT_KEY=TEST-PRODUCT-KEY\nSPX_BASE_URL=http://fallback:8000\n",
        encoding="utf-8",
    )

    values = mcp_workspace.read_seeded_workspace_env(
        primary_seed_env_path=primary_env,
        fallback_seed_env_path=fallback_env,
    )

    assert values["SPX_PRODUCT_KEY"] == "TEST-PRODUCT-KEY"
    assert values["SPX_BASE_URL"] == "http://fallback:8000"


def test_read_process_seed_env_prefers_valid_shell_values(monkeypatch) -> None:
    monkeypatch.setenv("SPX_PRODUCT_KEY", "TEST-PRODUCT-KEY")
    monkeypatch.setenv("SPX_BASE_URL", "http://shell-host:8000/")

    values = mcp_workspace.read_process_seed_env()

    assert values == {
        "SPX_PRODUCT_KEY": "TEST-PRODUCT-KEY",
        "SPX_BASE_URL": "http://shell-host:8000",
    }


def test_read_process_seed_env_ignores_placeholder_product_key(monkeypatch) -> None:
    monkeypatch.setenv("SPX_PRODUCT_KEY", "REPLACE_ME")
    monkeypatch.setenv("SPX_BASE_URL", "http://shell-host:8000/")

    values = mcp_workspace.read_process_seed_env()

    assert values == {
        "SPX_BASE_URL": "http://shell-host:8000",
    }


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


def test_resolve_workspace_contract_defaults_to_repo_dev(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"

    workspace_kind, work_mode = mcp_workspace.resolve_workspace_contract(
        workspace_dir=workspace,
        explicit_workspace_kind=None,
        explicit_work_mode=None,
    )

    assert workspace_kind == mcp_workspace.WORKSPACE_KIND_GIT
    assert work_mode == mcp_workspace.WORK_MODE_REPO_DEV


def test_resolve_workspace_selection_prompts_and_can_override_suggested_mode(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / "workspace"
    prompted_defaults: list[str] = []

    monkeypatch.setattr(mcp_workspace, "is_interactive_session", lambda: True)
    monkeypatch.setattr(
        mcp_workspace,
        "prompt_work_mode",
        lambda default_mode: prompted_defaults.append(default_mode) or mcp_workspace.WORK_MODE_RUNTIME_MCP,
    )

    workspace_kind, work_mode = mcp_workspace.resolve_workspace_selection(
        workspace_dir=workspace,
        explicit_workspace_kind=None,
        explicit_work_mode=None,
    )

    assert prompted_defaults == [mcp_workspace.WORK_MODE_REPO_DEV]
    assert workspace_kind == mcp_workspace.WORKSPACE_KIND_MANAGED
    assert work_mode == mcp_workspace.WORK_MODE_RUNTIME_MCP


def test_resolve_workspace_selection_skips_prompt_for_explicit_mode(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / "workspace"

    monkeypatch.setattr(mcp_workspace, "is_interactive_session", lambda: True)
    monkeypatch.setattr(
        mcp_workspace,
        "prompt_work_mode",
        lambda default_mode: (_ for _ in ()).throw(AssertionError("prompt should not run")),
    )

    workspace_kind, work_mode = mcp_workspace.resolve_workspace_selection(
        workspace_dir=workspace,
        explicit_workspace_kind=None,
        explicit_work_mode=mcp_workspace.WORK_MODE_RUNTIME_MCP,
    )

    assert workspace_kind == mcp_workspace.WORKSPACE_KIND_MANAGED
    assert work_mode == mcp_workspace.WORK_MODE_RUNTIME_MCP


def test_resolve_workspace_contract_prefers_local_mode_file_over_metadata(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    mcp_workspace.write_workspace_mode_file(workspace, mcp_workspace.WORK_MODE_RUNTIME_MCP)
    (workspace / mcp_workspace.WORKSPACE_MARKER_NAME).write_text(
        json.dumps(
            {
                "kind": mcp_workspace.WORKSPACE_MARKER_KIND,
                "workspace_kind": mcp_workspace.WORKSPACE_KIND_GIT,
                "default_work_mode": mcp_workspace.WORK_MODE_REPO_DEV,
            }
        ),
        encoding="utf-8",
    )

    workspace_kind, work_mode = mcp_workspace.resolve_workspace_contract(
        workspace_dir=workspace,
        explicit_workspace_kind=None,
        explicit_work_mode=None,
    )

    assert workspace_kind == mcp_workspace.WORKSPACE_KIND_MANAGED
    assert work_mode == mcp_workspace.WORK_MODE_RUNTIME_MCP


def test_marker_default_work_mode_supports_legacy_workspace_mode() -> None:
    work_mode = mcp_workspace.marker_default_work_mode(
        {"workspace_mode": mcp_workspace.WORKSPACE_KIND_GIT}
    )

    assert work_mode == mcp_workspace.WORK_MODE_REPO_DEV


def test_find_duplicate_workspace_entries_flags_finder_style_copies(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "docs").mkdir()
    (workspace / "docs 2").mkdir()
    (workspace / ".codex").mkdir()
    (workspace / ".codex 3").mkdir()
    (workspace / "notes 2").write_text("keep\n", encoding="utf-8")

    duplicates = mcp_workspace.find_duplicate_workspace_entries(workspace)

    assert duplicates == [(".codex 3", ".codex"), ("docs 2", "docs")]


def test_assert_workspace_ready_for_managed_bootstrap_rejects_git_checkout(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / ".git").mkdir(parents=True)

    with pytest.raises(RuntimeError, match="runtime_mcp uses an installer-managed workspace"):
        mcp_workspace.assert_workspace_ready_for_managed_bootstrap(workspace)


def test_assert_workspace_marker_consistency_rejects_broken_git_metadata(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "README.md").write_text("stale\n", encoding="utf-8")
    (workspace / mcp_workspace.WORKSPACE_MARKER_NAME).write_text(
        json.dumps(
            {
                "kind": mcp_workspace.WORKSPACE_MARKER_KIND,
                "workspace_kind": mcp_workspace.WORKSPACE_KIND_GIT,
                "default_work_mode": mcp_workspace.WORK_MODE_REPO_DEV,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="should be a git-backed repo_dev workspace"):
        mcp_workspace.assert_workspace_marker_consistency(workspace)


def test_prepare_git_workspace_clones_missing_workspace(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    calls: list[list[str]] = []

    def fake_run(argv, *, cwd=None, capture_output=False):
        calls.append(argv)
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(mcp_workspace, "run_command", fake_run)

    mcp_workspace.prepare_git_workspace(
        workspace,
        git_remote_url="https://example.com/spx-examples.git",
        git_branch="develop",
        replace_existing=False,
    )

    assert calls == [[
        "git",
        "clone",
        "--branch",
        "develop",
        "--single-branch",
        "https://example.com/spx-examples.git",
        str(workspace),
    ]]


def test_prepare_git_workspace_reuses_existing_git_checkout(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    (workspace / ".git").mkdir(parents=True)

    def fail_run(argv, *, cwd=None, capture_output=False):
        raise AssertionError(f"unexpected command: {argv}")

    monkeypatch.setattr(mcp_workspace, "run_command", fail_run)

    mcp_workspace.prepare_git_workspace(
        workspace,
        git_remote_url="https://example.com/spx-examples.git",
        git_branch="develop",
        replace_existing=False,
    )


def test_prepare_git_workspace_requires_replace_for_existing_non_git_dir(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "README.md").write_text("old\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="replace-existing-workspace"):
        mcp_workspace.prepare_git_workspace(
            workspace,
            git_remote_url="https://example.com/spx-examples.git",
            git_branch="develop",
            replace_existing=False,
        )


def test_prepare_git_workspace_replaces_existing_non_git_dir(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    stale_file = workspace / "README.md"
    stale_file.write_text("old\n", encoding="utf-8")
    calls: list[list[str]] = []

    def fake_run(argv, *, cwd=None, capture_output=False):
        calls.append(argv)
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(mcp_workspace, "run_command", fake_run)

    mcp_workspace.prepare_git_workspace(
        workspace,
        git_remote_url="https://example.com/spx-examples.git",
        git_branch="develop",
        replace_existing=True,
    )

    assert not stale_file.exists()
    assert calls == [[
        "git",
        "clone",
        "--branch",
        "develop",
        "--single-branch",
        "https://example.com/spx-examples.git",
        str(workspace),
    ]]


def test_prepare_git_workspace_rejects_duplicate_entries(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "docs").mkdir()
    (workspace / "docs 2").mkdir()

    with pytest.raises(RuntimeError, match="mixed or Finder-copied workspace"):
        mcp_workspace.prepare_git_workspace(
            workspace,
            git_remote_url="https://example.com/spx-examples.git",
            git_branch="develop",
            replace_existing=False,
        )


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
        "--no-input",
        "-e",
        str(workspace),
    ]


def test_bootstrap_codex_enables_write_tools(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    tools_dir = workspace / "tools"
    tools_dir.mkdir(parents=True)
    (tools_dir / "codex_mcp_bootstrap.py").write_text("", encoding="utf-8")
    calls: list[tuple[list[str], Path | None]] = []

    def fake_run(argv, *, cwd=None, capture_output=False):
        calls.append((argv, cwd))
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(mcp_workspace, "run_command", fake_run)

    mcp_workspace.bootstrap_codex(
        workspace,
        "python3.11",
        server_name="spx",
        allow_write=True,
        update_git_exclude=False,
    )

    assert calls == [([
        "python3.11",
        str(workspace / "tools" / "codex_mcp_bootstrap.py"),
        "--repo-root",
        str(workspace),
        "--server-name",
        "spx",
        "--skip-git-exclude",
    ], workspace)]


def test_bootstrap_codex_supports_explicit_read_only_mode(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    tools_dir = workspace / "tools"
    tools_dir.mkdir(parents=True)
    (tools_dir / "codex_mcp_bootstrap.py").write_text("", encoding="utf-8")
    calls: list[tuple[list[str], Path | None]] = []

    def fake_run(argv, *, cwd=None, capture_output=False):
        calls.append((argv, cwd))
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(mcp_workspace, "run_command", fake_run)

    mcp_workspace.bootstrap_codex(
        workspace,
        "python3.11",
        server_name="spx",
        allow_write=False,
        update_git_exclude=False,
    )

    assert calls == [([
        "python3.11",
        str(workspace / "tools" / "codex_mcp_bootstrap.py"),
        "--repo-root",
        str(workspace),
        "--server-name",
        "spx",
        "--skip-git-exclude",
        "--read-only",
    ], workspace)]


def test_bootstrap_codex_updates_git_exclude_for_git_workspaces(
    tmp_path: Path,
    monkeypatch,
) -> None:
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
        update_git_exclude=True,
    )

    assert calls == [[
        "python3.11",
        str(workspace / "tools" / "codex_mcp_bootstrap.py"),
        "--repo-root",
        str(workspace),
        "--server-name",
        "spx",
        "--read-only",
    ]]


def test_write_workspace_mode_file_is_idempotent(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    mcp_workspace.write_workspace_mode_file(workspace, mcp_workspace.WORK_MODE_RUNTIME_MCP)
    first = mcp_workspace.read_workspace_mode_file(workspace)
    mcp_workspace.write_workspace_mode_file(workspace, mcp_workspace.WORK_MODE_RUNTIME_MCP)
    second = mcp_workspace.read_workspace_mode_file(workspace)

    assert first == mcp_workspace.WORK_MODE_RUNTIME_MCP
    assert second == mcp_workspace.WORK_MODE_RUNTIME_MCP


def test_write_workspace_marker_and_mode_file_remain_consistent_for_managed_workspace(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    mcp_workspace.write_workspace_mode_file(workspace, mcp_workspace.WORK_MODE_RUNTIME_MCP)

    mcp_workspace.write_workspace_marker(
        workspace,
        source_root=tmp_path / "source",
        repo_root=workspace,
        workspace_python=workspace / ".venv" / "bin" / "python",
        server_name="spx",
        allow_write=False,
        workspace_kind=mcp_workspace.WORKSPACE_KIND_MANAGED,
        work_mode=mcp_workspace.WORK_MODE_RUNTIME_MCP,
        git_remote_url="https://example.com/spx-examples.git",
        git_branch="develop",
    )

    marker = mcp_workspace.read_workspace_marker(workspace)

    assert marker is not None
    assert marker["workspace_kind"] == mcp_workspace.WORKSPACE_KIND_MANAGED
    assert marker["default_work_mode"] == mcp_workspace.WORK_MODE_RUNTIME_MCP
    assert mcp_workspace.read_workspace_mode_file(workspace) == mcp_workspace.WORK_MODE_RUNTIME_MCP


def test_write_workspace_marker_and_mode_file_remain_consistent_for_git_workspace(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    mcp_workspace.write_workspace_mode_file(workspace, mcp_workspace.WORK_MODE_REPO_DEV)

    mcp_workspace.write_workspace_marker(
        workspace,
        source_root=tmp_path / "source",
        repo_root=workspace,
        workspace_python=workspace / ".venv" / "bin" / "python",
        server_name="spx",
        allow_write=False,
        workspace_kind=mcp_workspace.WORKSPACE_KIND_GIT,
        work_mode=mcp_workspace.WORK_MODE_REPO_DEV,
        git_remote_url="https://example.com/spx-examples.git",
        git_branch="develop",
    )

    marker = mcp_workspace.read_workspace_marker(workspace)

    assert marker is not None
    assert marker["workspace_kind"] == mcp_workspace.WORKSPACE_KIND_GIT
    assert marker["default_work_mode"] == mcp_workspace.WORK_MODE_REPO_DEV
    assert mcp_workspace.read_workspace_mode_file(workspace) == mcp_workspace.WORK_MODE_REPO_DEV


def test_main_managed_bootstrap_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    source_root = build_minimal_workspace_source(tmp_path / "source")
    monkeypatch.delenv("SPX_PRODUCT_KEY", raising=False)
    monkeypatch.delenv("SPX_BASE_URL", raising=False)
    (source_root / ".env").write_text("SPX_PRODUCT_KEY=TEST-PRODUCT-KEY\n", encoding="utf-8")
    workspace = tmp_path / "workspace"
    expected_python = workspace / ".venv" / "bin" / "python"

    def fake_bootstrap_runtime(repo_root: Path, workspace_dir: Path, python_bin: str) -> Path:
        expected_python.parent.mkdir(parents=True, exist_ok=True)
        expected_python.write_text("", encoding="utf-8")
        return expected_python

    bootstrap_codex_calls: list[bool] = []

    def fake_bootstrap_codex(
        workspace_dir: Path,
        python_bin: str,
        *,
        server_name: str,
        allow_write: bool,
        update_git_exclude: bool,
    ) -> None:
        bootstrap_codex_calls.append(allow_write)
        codex_dir = workspace_dir / ".codex"
        codex_dir.mkdir(parents=True, exist_ok=True)
        args = ['"-m"', '"spx_mcp"', '"stdio"']
        if allow_write:
            args.append('"--allow-write"')
        (codex_dir / "config.toml").write_text(
            "[mcp_servers.spx]\n"
            'command = "python3.11"\n'
            f"args = [{', '.join(args)}]\n",
            encoding="utf-8",
        )

    monkeypatch.setattr(mcp_workspace, "bootstrap_runtime", fake_bootstrap_runtime)
    monkeypatch.setattr(mcp_workspace, "bootstrap_codex", fake_bootstrap_codex)
    monkeypatch.setattr(mcp_workspace, "verify_workspace", lambda *args, **kwargs: None)

    argv = [
        "--source-root",
        str(source_root),
        "--workspace-dir",
        str(workspace),
        "--workspace-kind",
        mcp_workspace.WORKSPACE_KIND_MANAGED,
        "--work-mode",
        mcp_workspace.WORK_MODE_RUNTIME_MCP,
        "--python",
        "python3.11",
    ]

    assert mcp_workspace.main(argv) == 0
    assert mcp_workspace.main(argv) == 0

    marker = mcp_workspace.read_workspace_marker(workspace)
    assert marker is not None
    assert marker["allow_write"] is True
    assert marker["workspace_kind"] == mcp_workspace.WORKSPACE_KIND_MANAGED
    assert marker["default_work_mode"] == mcp_workspace.WORK_MODE_RUNTIME_MCP
    assert mcp_workspace.read_workspace_mode_file(workspace) == mcp_workspace.WORK_MODE_RUNTIME_MCP
    assert mcp_workspace.read_dotenv(workspace / ".env")["SPX_PRODUCT_KEY"] == "TEST-PRODUCT-KEY"
    assert bootstrap_codex_calls == [True, True]


def test_main_managed_bootstrap_respects_explicit_read_only(tmp_path: Path, monkeypatch) -> None:
    source_root = build_minimal_workspace_source(tmp_path / "source")
    workspace = tmp_path / "workspace"
    expected_python = workspace / ".venv" / "bin" / "python"
    bootstrap_codex_calls: list[bool] = []

    def fake_bootstrap_runtime(repo_root: Path, workspace_dir: Path, python_bin: str) -> Path:
        expected_python.parent.mkdir(parents=True, exist_ok=True)
        expected_python.write_text("", encoding="utf-8")
        return expected_python

    def fake_bootstrap_codex(
        workspace_dir: Path,
        python_bin: str,
        *,
        server_name: str,
        allow_write: bool,
        update_git_exclude: bool,
    ) -> None:
        bootstrap_codex_calls.append(allow_write)
        codex_dir = workspace_dir / ".codex"
        codex_dir.mkdir(parents=True, exist_ok=True)
        (codex_dir / "config.toml").write_text(
            "[mcp_servers.spx]\n"
            'command = "python3.11"\n'
            'args = ["-m", "spx_mcp", "stdio"]\n',
            encoding="utf-8",
        )

    monkeypatch.setattr(mcp_workspace, "bootstrap_runtime", fake_bootstrap_runtime)
    monkeypatch.setattr(mcp_workspace, "bootstrap_codex", fake_bootstrap_codex)
    monkeypatch.setattr(mcp_workspace, "verify_workspace", lambda *args, **kwargs: None)

    assert mcp_workspace.main([
        "--source-root",
        str(source_root),
        "--workspace-dir",
        str(workspace),
        "--workspace-kind",
        mcp_workspace.WORKSPACE_KIND_MANAGED,
        "--work-mode",
        mcp_workspace.WORK_MODE_RUNTIME_MCP,
        "--python",
        "python3.11",
        "--read-only",
    ]) == 0

    marker = mcp_workspace.read_workspace_marker(workspace)
    assert marker is not None
    assert marker["allow_write"] is False
    assert bootstrap_codex_calls == [False]


def test_main_git_bootstrap_sets_repo_dev_and_does_not_sync_managed_copy(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = build_minimal_workspace_source(tmp_path / "workspace")
    (workspace / ".git").mkdir()
    source_root = tmp_path / "source"
    source_root.mkdir()
    expected_python = workspace / ".venv" / "bin" / "python"

    def fake_bootstrap_runtime(repo_root: Path, workspace_dir: Path, python_bin: str) -> Path:
        expected_python.parent.mkdir(parents=True, exist_ok=True)
        expected_python.write_text("", encoding="utf-8")
        return expected_python

    bootstrap_codex_calls: list[bool] = []

    def fake_bootstrap_codex(
        workspace_dir: Path,
        python_bin: str,
        *,
        server_name: str,
        allow_write: bool,
        update_git_exclude: bool,
    ) -> None:
        bootstrap_codex_calls.append(allow_write)
        codex_dir = workspace_dir / ".codex"
        codex_dir.mkdir(parents=True, exist_ok=True)
        (codex_dir / "config.toml").write_text(
            "[mcp_servers.spx]\n"
            'command = "python3.11"\n'
            'args = ["-m", "spx_mcp", "stdio", "--allow-write"]\n',
            encoding="utf-8",
        )

    monkeypatch.setattr(mcp_workspace, "bootstrap_runtime", fake_bootstrap_runtime)
    monkeypatch.setattr(mcp_workspace, "bootstrap_codex", fake_bootstrap_codex)
    monkeypatch.setattr(mcp_workspace, "verify_workspace", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        mcp_workspace,
        "sync_payload",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("sync_payload should not run for repo_dev git workspaces")),
    )

    argv = [
        "--source-root",
        str(source_root),
        "--workspace-dir",
        str(workspace),
        "--workspace-kind",
        mcp_workspace.WORKSPACE_KIND_GIT,
        "--work-mode",
        mcp_workspace.WORK_MODE_REPO_DEV,
        "--python",
        "python3.11",
    ]

    assert mcp_workspace.main(argv) == 0

    marker = mcp_workspace.read_workspace_marker(workspace)
    assert marker is not None
    assert marker["allow_write"] is True
    assert marker["workspace_kind"] == mcp_workspace.WORKSPACE_KIND_GIT
    assert marker["default_work_mode"] == mcp_workspace.WORK_MODE_REPO_DEV
    assert mcp_workspace.read_workspace_mode_file(workspace) == mcp_workspace.WORK_MODE_REPO_DEV
    assert bootstrap_codex_calls == [True]


def test_write_workspace_readme_describes_git_mode(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    mcp_workspace.write_workspace_readme(
        workspace,
        server_name="spx",
        allow_write=False,
        workspace_kind=mcp_workspace.WORKSPACE_KIND_GIT,
        work_mode=mcp_workspace.WORK_MODE_REPO_DEV,
        git_remote_url="https://example.com/spx-examples.git",
        git_branch="develop",
    )

    readme = (workspace / mcp_workspace.WORKSPACE_README_NAME).read_text(encoding="utf-8")
    assert "workspace kind: `git`" in readme
    assert "default work mode: `repo_dev`" in readme
    assert "full Git clone" in readme
    assert "read/write mode" in readme
    assert "https://example.com/spx-examples.git" in readme
    assert "`develop`" in readme


def test_verify_workspace_checks_config_and_required_runtime_write_tools(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / "workspace"
    codex_dir = workspace / ".codex"
    codex_dir.mkdir(parents=True)
    (codex_dir / "config.toml").write_text(
        "[mcp_servers.spx]\n"
        'command = "python3.11"\n'
        'args = ["-m", "spx_mcp", "stdio", "--allow-write"]\n',
        encoding="utf-8",
    )
    calls: list[list[str]] = []

    def fake_run(argv, *, cwd=None, capture_output=False):
        calls.append(list(argv))
        if "doctor" in argv:
            return SimpleNamespace(stdout=json.dumps({"ok": True, "problems": []}))
        return SimpleNamespace(
            stdout=json.dumps(
                [{"name": name, "write": True} for name in mcp_workspace.REQUIRED_RUNTIME_WRITE_TOOLS]
            )
        )

    monkeypatch.setattr(mcp_workspace, "run_command", fake_run)

    mcp_workspace.verify_workspace(
        tmp_path / ".venv" / "bin" / "python",
        workspace,
        server_name="spx",
        allow_write=True,
    )

    assert calls == [
        [
            str(tmp_path / ".venv" / "bin" / "python"),
            "-m",
            "spx_mcp",
            "doctor",
            "--repo-root",
            str(workspace),
            "--json",
            "--allow-write",
        ],
        [
            str(tmp_path / ".venv" / "bin" / "python"),
            "-m",
            "spx_mcp",
            "list-tools",
            "--json",
            "--allow-write",
        ],
    ]


def test_verify_workspace_fails_when_required_runtime_write_tools_are_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / "workspace"
    codex_dir = workspace / ".codex"
    codex_dir.mkdir(parents=True)
    (codex_dir / "config.toml").write_text(
        "[mcp_servers.spx]\n"
        'command = "python3.11"\n'
        'args = ["-m", "spx_mcp", "stdio", "--allow-write"]\n',
        encoding="utf-8",
    )

    def fake_run(argv, *, cwd=None, capture_output=False):
        if "doctor" in argv:
            return SimpleNamespace(stdout=json.dumps({"ok": True, "problems": []}))
        return SimpleNamespace(
            stdout=json.dumps(
                [{"name": "server_register_model_from_catalog", "write": True}]
            )
        )

    monkeypatch.setattr(mcp_workspace, "run_command", fake_run)

    with pytest.raises(RuntimeError, match="server_register_model_and_ensure_instance"):
        mcp_workspace.verify_workspace(
            tmp_path / ".venv" / "bin" / "python",
            workspace,
            server_name="spx",
            allow_write=True,
        )


def test_verify_workspace_reports_doctor_problems_from_nonzero_json(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / "workspace"
    codex_dir = workspace / ".codex"
    codex_dir.mkdir(parents=True)
    (codex_dir / "config.toml").write_text(
        "[mcp_servers.spx]\n"
        'command = "python3.11"\n'
        'args = ["-m", "spx_mcp", "stdio", "--allow-write"]\n',
        encoding="utf-8",
    )

    def fake_run(argv, *, cwd=None, capture_output=False):
        if "doctor" in argv:
            raise subprocess.CalledProcessError(
                1,
                argv,
                output=json.dumps(
                    {
                        "ok": False,
                        "problems": ["SPX_PRODUCT_KEY is missing or invalid for this MCP workspace."],
                    }
                ),
                stderr="",
            )
        raise AssertionError(f"unexpected command: {argv}")

    monkeypatch.setattr(mcp_workspace, "run_command", fake_run)

    with pytest.raises(RuntimeError, match="SPX_PRODUCT_KEY is missing or invalid"):
        mcp_workspace.verify_workspace(
            tmp_path / ".venv" / "bin" / "python",
            workspace,
            server_name="spx",
            allow_write=True,
        )
