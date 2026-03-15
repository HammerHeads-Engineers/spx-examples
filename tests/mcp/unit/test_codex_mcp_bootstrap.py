# SPDX-License-Identifier: MIT

from pathlib import Path

from tools.codex_mcp_bootstrap import (
    detect_server_invocation,
    ensure_exclude_pattern,
    render_mcp_server_block,
    upsert_named_mcp_server,
)


def test_detect_server_invocation_prefers_local_venv_windows(tmp_path) -> None:
    python_exe = tmp_path / ".venv" / "Scripts" / "python.exe"
    python_exe.parent.mkdir(parents=True)
    python_exe.write_text("", encoding="utf-8")

    invocation, strategy = detect_server_invocation(
        tmp_path,
        allow_write=True,
        startup_timeout_sec=20,
        tool_timeout_sec=120,
        platform_name="win32",
        which=lambda _: None,
    )

    assert strategy == "local-venv"
    assert invocation.command == python_exe.resolve().as_posix()
    assert invocation.args == ["-m", "spx_mcp", "stdio", "--allow-write"]
    assert invocation.cwd == tmp_path.resolve().as_posix()


def test_detect_server_invocation_falls_back_to_poetry(tmp_path) -> None:
    invocation, strategy = detect_server_invocation(
        tmp_path,
        allow_write=False,
        startup_timeout_sec=15,
        tool_timeout_sec=90,
        platform_name="linux",
        which=lambda name: "/usr/bin/poetry" if name == "poetry" else None,
    )

    assert strategy == "poetry"
    assert invocation.command == "poetry"
    assert invocation.args == ["run", "python", "-m", "spx_mcp", "stdio"]


def test_upsert_named_mcp_server_replaces_existing_section() -> None:
    existing = (
        "[mcp_servers.spx]\n"
        'command = "old"\n'
        "args = []\n\n"
        "[model]\n"
        'name = "keep"\n'
    )
    replacement = render_mcp_server_block(
        "spx",
        detect_server_invocation(
            Path("."),
            allow_write=True,
            startup_timeout_sec=20,
            tool_timeout_sec=120,
            platform_name="linux",
            which=lambda name: f"/usr/bin/{name}" if name == "python3" else None,
        )[0],
    )

    updated = upsert_named_mcp_server(existing, "spx", replacement)

    assert 'command = "old"' not in updated
    assert updated.count("[mcp_servers.spx]") == 1
    assert '[model]\nname = "keep"' in updated


def test_ensure_exclude_pattern_is_idempotent() -> None:
    updated, changed = ensure_exclude_pattern("", ".codex/config.toml")

    assert changed is True
    assert updated == ".codex/config.toml\n"

    updated_again, changed_again = ensure_exclude_pattern(
        updated,
        ".codex/config.toml",
    )

    assert changed_again is False
    assert updated_again == ".codex/config.toml\n"
