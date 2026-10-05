"""Contract tests for the provider-independent Setup handoff."""

import json
from pathlib import Path
import sys

import pytest

from installer.setup_session import SetupEngine
from installer.setup_workspace import prepare_workspace, read_descriptor

KEY = "AAAAA-AAAAA-AAAAA-AAAAA-AAAAA-AAAAA"


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path / "Workspace with spaces Łódź"
    engine = SetupEngine(tmp_path / "private")
    session = engine.create(tmp_path / "generated", KEY, initial={"start": False})
    prepare_workspace(
        root,
        engine,
        session["session_id"],
        python=Path(sys.executable),
        bootstrap=False,
    )
    return root, engine, session


def test_profiles_and_instructions_do_not_contain_key(workspace):
    root, engine, session = workspace
    descriptor = read_descriptor(root)
    assert descriptor["session_id"] == session["session_id"]
    for name in (
        "AGENTS.md",
        "CLAUDE.md",
        "INSTALLATION.md",
        ".codex/config.toml",
        ".mcp.json",
        "opencode.jsonc",
        "setup-session.json",
    ):
        assert KEY not in (root / name).read_text(encoding="utf-8")
    claude = json.loads((root / ".mcp.json").read_text(encoding="utf-8"))
    assert any(
        value.endswith("setup_mcp.py")
        for value in claude["mcpServers"]["spx_setup"]["args"]
    )
    opencode = json.loads((root / "opencode.jsonc").read_text(encoding="utf-8"))
    assert opencode["mcp"]["servers"]["spx_setup"]["type"] == "local"
    assert "mcp.servers" not in opencode


def test_preparation_preserves_other_client_settings(workspace):
    root, engine, session = workspace
    (root / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"other": {"command": "other"}}, "extra": True})
    )
    (root / "opencode.jsonc").write_text(
        '// user settings\n{"theme":"dark","mcp":{"servers":{"other":{"type":"local","command":["other"]}}}}'
    )
    with (root / ".codex/config.toml").open("a") as handle:
        handle.write('\n[mcp_servers.other]\ncommand = "other"\n')
    prepare_workspace(
        root,
        engine,
        session["session_id"],
        python=Path(sys.executable),
        bootstrap=False,
    )
    assert json.loads((root / ".mcp.json").read_text(encoding="utf-8"))["extra"] is True
    assert (
        json.loads((root / "opencode.jsonc").read_text(encoding="utf-8"))["theme"]
        == "dark"
    )
    assert "[mcp_servers.other]" in (root / ".codex/config.toml").read_text()


@pytest.mark.skipif(
    sys.version_info < (3, 10),
    reason="Setup MCP requires Python >=3.10; required 3.12 tests cover the MCP server",
)
def test_mcp_exposes_only_setup_tools_without_api(workspace):
    import asyncio
    from installer.setup_mcp import build_server

    root, _, _ = workspace
    server = build_server(root)
    names = {tool.name for tool in asyncio.run(server.list_tools())}
    assert names == {
        "setup_get_session",
        "setup_list_options",
        "setup_update_selection",
        "setup_plan",
        "setup_apply",
        "setup_get_status",
    }


def test_runtime_workspace_is_never_overwritten(tmp_path):
    root = tmp_path / "existing-runtime"
    root.mkdir()
    (root / "AGENTS.md").write_text("runtime instructions")
    engine = SetupEngine(tmp_path / "private")
    session = engine.create(tmp_path / "generated", KEY)
    with pytest.raises(Exception, match="workspace"):
        prepare_workspace(
            root,
            engine,
            session["session_id"],
            python=Path(sys.executable),
            bootstrap=False,
        )
    assert (root / "AGENTS.md").read_text() == "runtime instructions"


@pytest.mark.skipif(
    sys.version_info < (3, 10),
    reason="Setup MCP requires Python >=3.10; the required 3.12 job covers its stdio contract",
)
def test_real_stdio_handoff_survives_reconnect_and_generates_configuration(
    workspace, tmp_path
):
    import asyncio
    import os
    import time
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    root, engine, session = workspace
    profile = json.loads((root / ".mcp.json").read_text(encoding="utf-8"))[
        "mcpServers"
    ]["spx_setup"]
    parameters = StdioServerParameters(
        command=profile["command"],
        args=profile["args"],
        cwd=str(tmp_path),
        env={
            **os.environ,
            "SPX_PRODUCT_KEY": "stale-host-key",
            "SPX_BASE_URL": "http://invalid.invalid",
        },
    )

    async def first_connection():
        async with stdio_client(parameters) as (reader, writer):
            async with ClientSession(reader, writer) as client:
                await client.initialize()
                options = await client.call_tool(
                    "setup_list_options", {"session_id": session["session_id"]}
                )
                assert json.loads(options.content[0].text)["ok"]
                assert KEY not in options.content[0].text
                result = await client.call_tool(
                    "setup_update_selection",
                    {
                        "session_id": session["session_id"],
                        "selection": {"protocols": ["http"], "start": False},
                    },
                )
                assert json.loads(result.content[0].text)["ok"]
                result = await client.call_tool(
                    "setup_plan", {"session_id": session["session_id"]}
                )
                plan = json.loads(result.content[0].text)["result"]
                assert plan["ready"] and KEY not in result.content[0].text
                result = await client.call_tool(
                    "setup_apply",
                    {
                        "session_id": session["session_id"],
                        "plan_id": plan["plan_id"],
                        "revision": plan["revision"],
                    },
                )
                assert json.loads(result.content[0].text)["ok"]

    asyncio.run(first_connection())

    async def reconnect():
        async with stdio_client(parameters) as (reader, writer):
            async with ClientSession(reader, writer) as client:
                await client.initialize()
                for _ in range(60):
                    result = await client.call_tool(
                        "setup_get_status", {"session_id": session["session_id"]}
                    )
                    current = json.loads(result.content[0].text)["result"]
                    if current["status"] in {
                        "SUCCEEDED",
                        "FAILED",
                        "RECOVERY_REQUIRED",
                    }:
                        assert current["status"] == "SUCCEEDED", current
                        return
                    await asyncio.sleep(0.25)
                pytest.fail("Detached Setup job did not finish")

    asyncio.run(reconnect())
    output = Path(session["output"])
    assert (output / "bundle.json").is_file()
    assert KEY in (output / ".env").read_text(encoding="utf-8")
    assert "stale-host-key" not in (output / ".env").read_text(encoding="utf-8")


def test_jsonc_preserves_strings_and_handles_trailing_commas():
    from installer.setup_workspace import _jsonc

    assert _jsonc('{"url":"https://host/a,}b","list":[1,], /*note*/}') == {
        "url": "https://host/a,}b",
        "list": [1],
    }


def test_invalid_client_settings_leave_all_profiles_unchanged(workspace):
    from installer.setup_session import SetupError

    root, engine, session = workspace
    codex = (root / ".codex/config.toml").read_bytes()
    claude = (root / ".mcp.json").read_bytes()
    broken = '{"mcp":{"servers":[]}}'
    (root / "opencode.jsonc").write_text(broken, encoding="utf-8")
    with pytest.raises(SetupError, match="preserved"):
        prepare_workspace(root, engine, session["session_id"], bootstrap=False)
    assert (root / ".codex/config.toml").read_bytes() == codex
    assert (root / ".mcp.json").read_bytes() == claude
    assert (root / "opencode.jsonc").read_text(encoding="utf-8") == broken


def test_bootstrap_uses_utf8_and_can_retry_failed_download(tmp_path, monkeypatch):
    import subprocess
    from installer.setup_session import SetupError

    root = tmp_path / "Workspace Łódź"
    engine = SetupEngine(tmp_path / "private")
    session = engine.create(tmp_path / "generated", KEY, initial={"start": False})
    calls = []
    # This is a bootstrap/decoder contract, not a live SDK installation; the
    # real 3.9 fallback is checked separately below.
    monkeypatch.setattr("installer.setup_workspace.sys.version_info", (3, 12))

    def run(command, **kwargs):
        calls.append(kwargs)
        assert kwargs["encoding"] == "utf-8"
        if len(calls) == 1:
            return subprocess.CompletedProcess(command, 1, "", "offline")
        return subprocess.CompletedProcess(command, 0, str(sys.executable), "")

    monkeypatch.setattr("installer.setup_workspace.subprocess.run", run)
    with pytest.raises(SetupError, match="runtime"):
        prepare_workspace(root, engine, session["session_id"])
    assert (root / ".spx-setup-workspace.json").is_file()
    prepare_workspace(root, engine, session["session_id"])
    assert len(calls) == 3  # failed bootstrap, retry, doctor


def test_unsupported_python_reports_agent_fallback(tmp_path, monkeypatch):
    from installer.setup_session import SetupError

    engine = SetupEngine(tmp_path / "private")
    session = engine.create(tmp_path / "generated", KEY, initial={"start": False})
    monkeypatch.setattr("installer.setup_workspace.sys.version_info", (3, 9))
    with pytest.raises(SetupError, match="Python 3.10.*legacy"):
        prepare_workspace(tmp_path / "workspace", engine, session["session_id"])


def test_workspace_cannot_contain_credentials_or_active_configuration(tmp_path):
    from installer.setup_session import SetupError

    engine = SetupEngine(tmp_path / "private")
    session = engine.create(tmp_path / "generated", KEY, initial={"start": False})
    for root in (engine.root, engine.root / "workspace", tmp_path / "generated"):
        with pytest.raises(SetupError, match="separate"):
            prepare_workspace(root, engine, session["session_id"], bootstrap=False)


def test_cli_launcher_preserves_unicode_paths(workspace):
    import os
    import subprocess

    root, _, session = workspace
    if os.name == "nt":
        command = [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(root / "setup-cli.ps1"),
        ]
    else:
        command = ["sh", str(root / "setup-cli.sh")]
    result = subprocess.run(
        [*command, "get-session", "--json"],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    public = json.loads(result.stdout)
    assert public["ok"] and public["result"]["session_id"] == session["session_id"]
    assert KEY not in result.stdout


def test_agent_key_prompt_does_not_reuse_stale_host_environment(monkeypatch, capsys):
    from installer.wizard import InstallerWizard

    monkeypatch.setenv("SPX_PRODUCT_KEY", "BBBBB-BBBBB-BBBBB-BBBBB-BBBBB-BBBBB")
    monkeypatch.setattr("installer.wizard.read_secret", lambda *a: KEY)
    assert (
        InstallerWizard(mode="legacy")._prompt_license_key(use_environment=False) == KEY
    )
    assert "Detected SPX_PRODUCT_KEY" not in capsys.readouterr().out


def test_replacing_workspace_invalidates_old_agent_draft(workspace, tmp_path):
    from installer.setup_session import SetupError

    root, engine, previous = workspace
    plan = engine.plan(previous["session_id"])
    new = engine.create(tmp_path / "other-output", KEY, initial={"start": False})
    prepare_workspace(root, engine, new["session_id"], bootstrap=False)
    assert engine.get(previous["session_id"])["status"] == "HANDED_BACK"
    with pytest.raises(SetupError):
        engine.apply(
            previous["session_id"], plan["plan_id"], plan["revision"], launch=False
        )


def test_return_to_wizard_invalidates_reviewed_agent_plan(workspace, monkeypatch):
    from installer.setup_session import SetupError
    from installer.setup_workspace import monitor

    _, engine, session = workspace
    plan = engine.plan(session["session_id"])
    monkeypatch.setattr("installer.terminal_selection.is_interactive", lambda: True)
    monkeypatch.setattr("installer.setup_workspace._return_requested", lambda: True)
    assert monitor(engine, session["session_id"]) is None
    assert engine.get(session["session_id"])["status"] == "HANDED_BACK"
    with pytest.raises(SetupError):
        engine.apply(
            session["session_id"], plan["plan_id"], plan["revision"], launch=False
        )


def test_closing_monitor_does_not_cancel_queued_job(workspace, monkeypatch):
    from installer.setup_workspace import monitor

    _, engine, session = workspace
    plan = engine.plan(session["session_id"])
    job = engine.apply(
        session["session_id"], plan["plan_id"], plan["revision"], launch=False
    )
    monkeypatch.setattr("installer.terminal_selection.is_interactive", lambda: True)

    def close():
        raise KeyboardInterrupt()

    monkeypatch.setattr("installer.setup_workspace._return_requested", close)
    assert monitor(engine, session["session_id"]) == 0
    assert engine.get(session["session_id"])["status"] == "APPLYING"
    engine.run_job(session["session_id"], job["job_id"])
    assert engine.get(session["session_id"])["status"] == "SUCCEEDED"
