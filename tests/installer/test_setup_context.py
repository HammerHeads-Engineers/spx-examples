"""Regressions from a persistent client seeing yesterday's completed Setup."""

import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from installer.setup_session import SetupEngine, SetupError, atomic_json
from installer.setup_workspace import prepare_workspace

KEY = "AAAAA-AAAAA-AAAAA-AAAAA-AAAAA-AAAAA"


@pytest.fixture
def workspace(tmp_path):
    engine = SetupEngine(tmp_path / "private")
    first = engine.create(tmp_path / "output", KEY, initial={"start": False})
    root = tmp_path / "workspace"
    prepare_workspace(root, engine, first["session_id"], bootstrap=False)
    return root, engine, first


def call(server, name, **arguments):
    result = asyncio.run(server.call_tool(name, arguments))
    if isinstance(result, tuple):
        result = result[0]
    return result if isinstance(result, dict) else json.loads(result[0].text)


def test_context_distinguishes_new_draft_from_committed_installation(workspace):
    from installer.setup_runtime import binding_path

    root, engine, first = workspace
    state = engine._read(first["session_id"])
    state.update(status="SUCCEEDED", stage="complete", tools={"ok": True})
    engine._write(state)
    atomic_json(
        binding_path(engine, first["output"]),
        {
            "session_id": first["session_id"],
            "api": "http://127.0.0.1:8000",
            "started": True,
        },
    )
    new = engine.create(Path(first["output"]), KEY, initial={"start": False})
    prepare_workspace(root, engine, new["session_id"], bootstrap=False)
    context = engine.context(new["session_id"])
    assert context["session"]["status"] == "DRAFT"
    assert context["installation"]["session_id"] == first["session_id"]
    assert context["installation"]["started"] is True
    assert context["installation"]["server_checked"] is False
    assert context["requirements_schema"] and context["missing_decisions"]
    assert context["license"]["instance_limit"] is None
    assert KEY not in json.dumps(context)


@pytest.mark.skipif(sys.version_info < (3, 10), reason="MCP SDK requires Python 3.10+")
def test_connected_mcp_resolves_latest_descriptor_and_rejects_old_writes(workspace):
    from installer.setup_mcp import build_server

    root, engine, first = workspace
    server = build_server(root)
    new = engine.create(Path(first["output"]), KEY, initial={"start": False})
    prepare_workspace(root, engine, new["session_id"], bootstrap=False)
    result = call(server, "setup_get_session")
    assert result["ok"] and result["result"]["session_id"] == new["session_id"]
    result = call(server, "setup_get_context")
    assert (
        result["ok"] and result["result"]["session"]["session_id"] == new["session_id"]
    )
    blocked = call(
        server,
        "setup_update_selection",
        session_id=first["session_id"],
        selection={"start": True},
    )
    assert not blocked["ok"] and blocked["error"]["code"] == "SESSION_MISMATCH"
    assert blocked["error"]["details"]["current_session_id"] == new["session_id"]
    assert not engine.get(new["session_id"])["selection"]["start"]


def test_runtime_catalog_and_binding_follow_current_workspace(workspace, tmp_path):
    from installer.setup_runtime import SetupRuntime, binding_path

    root, engine, first = workspace
    runtime = SetupRuntime(root)
    new = engine.create(tmp_path / "other-output", KEY, initial={"start": False})
    prepare_workspace(root, engine, new["session_id"], bootstrap=False)
    atomic_json(
        binding_path(engine, new["output"]),
        {
            "session_id": new["session_id"],
            "api": "http://127.0.0.1:18000",
            "started": True,
        },
    )
    assert runtime.config.spx_base_url == "http://127.0.0.1:18000"


def test_context_available_without_docker_or_server(workspace, monkeypatch):
    root, engine, first = workspace
    monkeypatch.setattr(
        engine, "_preflight", lambda *a: pytest.fail("Context ran Docker preflight")
    )
    result = engine.context(first["session_id"])
    assert result["installation"]["source"] == "none"
    assert result["installation"]["runtime_available"] is False
    assert result["session"]["status"] == "DRAFT"
    assert result["recommended_selection"]["instances"] == []


def test_cli_context_matches_engine_without_secrets(workspace, capsys):
    from installer.__main__ import main

    _, engine, first = workspace
    assert (
        main(
            [
                "setup",
                "--state-root",
                str(engine.root),
                "get-context",
                "--session-id",
                first["session_id"],
                "--json",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    result = json.loads(output)
    assert (
        result["ok"]
        and result["result"]["session"]["session_id"] == first["session_id"]
    )
    assert KEY not in output


def test_workspace_cli_follows_current_session_and_rejects_stale_apply(
    workspace, capsys
):
    from installer.__main__ import main

    root, engine, first = workspace
    new = engine.create(Path(first["output"]), KEY, initial={"start": False})
    prepare_workspace(root, engine, new["session_id"], bootstrap=False)
    prefix = ["setup", "--workspace-root", str(root)]
    assert main(prefix + ["get-context", "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["result"]["session"]["session_id"] == new["session_id"]
    assert (
        main(
            prefix
            + [
                "apply",
                "--session-id",
                first["session_id"],
                "--plan-id",
                "old-plan",
                "--revision",
                "1",
                "--json",
            ]
        )
        == 1
    )
    result = json.loads(capsys.readouterr().out)
    assert result["error"]["code"] == "SESSION_MISMATCH"
    assert result["error"]["details"]["current_session_id"] == new["session_id"]
    assert engine.get(new["session_id"])["status"] == "DRAFT"


def test_generated_launcher_reads_current_descriptor_without_regeneration(workspace):
    root, engine, first = workspace
    new = engine.create(Path(first["output"]), KEY, initial={"start": False})
    descriptor_path = root / "setup-session.json"
    descriptor = json.loads(descriptor_path.read_text())
    descriptor["session_id"] = new["session_id"]
    atomic_json(descriptor_path, descriptor)
    command = (
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(root / "setup-cli.ps1"),
        ]
        if os.name == "nt"
        else ["sh", str(root / "setup-cli.sh")]
    )
    response = subprocess.run(
        command + ["get-context", "--json"],
        capture_output=True,
        encoding="utf-8",
        timeout=30,
    )
    assert response.returncode == 0, response.stderr
    assert (
        json.loads(response.stdout)["result"]["session"]["session_id"]
        == new["session_id"]
    )
    assert KEY not in response.stdout


@pytest.mark.parametrize("pointer", [[], {}, {"workspace": 42, "session_id": "old"}])
def test_invalid_private_workspace_pointer_does_not_fall_back_to_old_session(
    workspace, pointer
):
    from installer.setup_runtime import binding_path
    from installer.setup_workspace import current_descriptor

    root, engine, first = workspace
    atomic_json(
        binding_path(engine, first["output"]).with_name("setup-workspace.json"), pointer
    )
    with pytest.raises(SetupError, match="Run SPX Setup"):
        current_descriptor(root)


def test_workspace_pointer_cannot_redirect_to_other_installation(workspace, tmp_path):
    from installer.setup_runtime import binding_path
    from installer.setup_workspace import current_descriptor

    root, engine, first = workspace
    other = engine.create(tmp_path / "unrelated-output", KEY, initial={"start": False})
    other_root = tmp_path / "unrelated-workspace"
    prepare_workspace(other_root, engine, other["session_id"], bootstrap=False)
    atomic_json(
        binding_path(engine, first["output"]).with_name("setup-workspace.json"),
        {"workspace": str(other_root), "session_id": other["session_id"]},
    )
    with pytest.raises(SetupError, match="Run SPX Setup"):
        current_descriptor(root)


@pytest.mark.skipif(sys.version_info < (3, 10), reason="MCP SDK requires Python 3.10+")
def test_old_workspace_follows_new_shared_workspace_for_same_installation(
    workspace, tmp_path
):
    from installer.setup_mcp import build_server
    from installer.setup_runtime import SetupRuntime, binding_path

    root, engine, first = workspace
    server = build_server(root)
    runtime = SetupRuntime(root)
    new = engine.create(Path(first["output"]), KEY, initial={"start": False})
    canonical = tmp_path / "new workspace"
    prepare_workspace(canonical, engine, new["session_id"], bootstrap=False)
    result = call(server, "setup_get_context")
    assert (
        result["ok"] and result["result"]["session"]["session_id"] == new["session_id"]
    )
    assert result["result"]["workspace"] == {
        "path": str(canonical.resolve()),
        "version": 1,
        "redirected": True,
    }
    atomic_json(
        binding_path(engine, new["output"]),
        {
            "session_id": new["session_id"],
            "api": "http://127.0.0.1:18000",
            "started": True,
        },
    )
    assert runtime.config.repo_root == canonical.resolve()
    assert runtime.config.spx_base_url == "http://127.0.0.1:18000"
    assert KEY not in json.dumps(result)


@pytest.mark.skipif(sys.version_info < (3, 10), reason="MCP SDK requires Python 3.10+")
def test_real_stdio_context_follows_rotated_descriptor(workspace):
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    root, engine, first = workspace
    profile = json.loads((root / ".mcp.json").read_text())["mcpServers"]["spx_setup"]
    parameters = StdioServerParameters(command=profile["command"], args=profile["args"])

    async def verify():
        async with stdio_client(parameters) as (reader, writer):
            async with ClientSession(reader, writer) as client:
                await client.initialize()

                async def invoke(name, args):
                    reply = await client.call_tool(name, args)
                    text = reply.content[0].text
                    assert KEY not in text
                    return json.loads(text)

                before = await invoke("setup_get_context", {})
                assert before["result"]["session"]["session_id"] == first["session_id"]
                new = engine.create(
                    Path(first["output"]), KEY, initial={"start": False}
                )
                descriptor_path = root / "setup-session.json"
                descriptor = json.loads(descriptor_path.read_text())
                descriptor["session_id"] = new["session_id"]
                atomic_json(descriptor_path, descriptor)
                after = await invoke("setup_get_context", {})
                assert after["result"]["session"]["session_id"] == new["session_id"]
                blocked = await invoke(
                    "setup_apply",
                    {
                        "session_id": first["session_id"],
                        "plan_id": "old-plan",
                        "revision": 1,
                    },
                )
                assert (
                    not blocked["ok"] and blocked["error"]["code"] == "SESSION_MISMATCH"
                )

    asyncio.run(verify())
