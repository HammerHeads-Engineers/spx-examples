"""Installation and live work must share one MCP connection and private binding."""

import asyncio
import json
import os
from pathlib import Path
import sys

import pytest

from installer.setup_session import SetupEngine, atomic_json
from installer.setup_workspace import prepare_workspace

KEY = "AAAAA-AAAAA-AAAAA-AAAAA-AAAAA-AAAAA"


@pytest.fixture
def workspace(tmp_path):
    engine = SetupEngine(tmp_path / "private")
    session = engine.create(tmp_path / "generated", KEY, initial={"start": False})
    root = tmp_path / "Workspace with spaces Łódź"
    prepare_workspace(root, engine, session["session_id"], bootstrap=False)
    return root, engine, session


@pytest.mark.skipif(sys.version_info < (3, 10), reason="MCP SDK requires Python 3.10+")
def test_both_connections_expose_their_tools_before_install(workspace):
    from installer.setup_mcp import build_server

    root, _, _ = workspace
    setup = {tool.name for tool in asyncio.run(build_server(root).list_tools())}
    runtime = {
        tool.name
        for tool in asyncio.run(build_server(root, toolset="runtime").list_tools())
    }
    assert "setup_plan" in setup
    assert "health" not in setup
    assert "setup_plan" not in runtime
    assert {
        "health",
        "repo_find_models",
        "server_list_models",
        "server_ensure_instance",
        "server_start_instance",
        "server_upsert_connection",
    } <= runtime


def test_all_flows_prepare_tools_after_success_without_changing_result(
    tmp_path, monkeypatch
):
    engine = SetupEngine(tmp_path / "state")
    session = engine.create(tmp_path / "output", KEY, initial={"start": False})
    calls = []

    def prepare(current, *, started):
        assert (Path(current["output"]) / "bundle.json").is_file()
        calls.append(started)
        return {"ok": True, "workspace": str(tmp_path / "tools")}

    monkeypatch.setattr(engine, "_prepare_tools", prepare)
    plan = engine.plan(session["session_id"])
    job = engine.apply(
        session["session_id"], plan["plan_id"], plan["revision"], launch=False
    )
    engine.run_job(session["session_id"], job["job_id"])
    state = engine.get(session["session_id"])
    assert state["status"] == "SUCCEEDED"
    assert state["tools"]["ok"]
    assert calls == [False]


def test_ordinary_wizard_prepares_mcp_before_deployment(tmp_path, monkeypatch):
    from installer.setup_local import execute_selection
    from installer.wizard import WizardSelection

    engine = SetupEngine(tmp_path / "private")
    monkeypatch.setattr("installer.setup_local.SetupEngine", lambda: engine)
    events = []

    def prepare(workspace, current_engine, session_id, **kwargs):
        assert current_engine is engine
        assert not (tmp_path / "generated" / "bundle.json").exists()
        events.append("mcp-prepared")

    monkeypatch.setattr("installer.setup_workspace.prepare_workspace", prepare)
    monkeypatch.setattr(
        engine,
        "_prepare_tools",
        lambda *args, **kwargs: {"ok": True, "workspace": str(tmp_path / "workspace")},
    )
    selection = WizardSelection(
        packages=[],
        profiles=[],
        protocols=[],
        install_examples=False,
        install_spx_ui=True,
        offline_bundle=False,
        license_key=KEY,
        model_ids=[],
        service_ids=[],
        instances=[],
        start_instances=[],
    )
    result = execute_selection(
        selection,
        tmp_path / "generated",
        workspace=tmp_path / "workspace",
        prepare_mcp_before_install=True,
    )
    assert events == ["mcp-prepared"]
    assert result["status"] == "SUCCEEDED"


def test_tool_failure_is_separate_from_successful_installation(tmp_path, monkeypatch):
    engine = SetupEngine(tmp_path / "state")
    session = engine.create(tmp_path / "output", KEY, initial={"start": False})

    def fail(*a, **k):
        raise RuntimeError("download failed with secret " + KEY)

    monkeypatch.setattr(engine, "_prepare_tools", fail)
    plan = engine.plan(session["session_id"])
    job = engine.apply(
        session["session_id"], plan["plan_id"], plan["revision"], launch=False
    )
    engine.run_job(session["session_id"], job["job_id"])
    state = engine.get(session["session_id"])
    assert state["status"] == "SUCCEEDED"
    assert state["tools"]["ok"] is False
    assert "MCP Setup" in state["mcp_warning"]
    assert (Path(session["output"]) / ".env").is_file()
    assert KEY not in json.dumps(state)


def test_same_runtime_object_reads_new_key_and_address_after_update(
    workspace, monkeypatch
):
    from installer.setup_runtime import SetupRuntime, binding_path

    root, engine, session = workspace
    path = binding_path(engine, session["output"])
    atomic_json(
        path,
        {
            "session_id": session["session_id"],
            "api": "http://127.0.0.1:8000",
            "started": True,
        },
    )
    runtime = SetupRuntime(root)
    monkeypatch.setenv("SPX_PRODUCT_KEY", "stale-host-key")
    monkeypatch.setenv("SPX_BASE_URL", "http://invalid.invalid")
    assert runtime.config.product_key == KEY
    updated = engine.create(Path(session["output"]), "B" * 30, initial={"start": False})
    atomic_json(
        path,
        {
            "session_id": updated["session_id"],
            "api": "http://127.0.0.1:18000",
            "started": True,
        },
    )
    assert runtime.config.product_key == "B" * 30
    assert runtime.config.spx_base_url == "http://127.0.0.1:18000"
    # Rollback retains/restores the old binding without restarting MCP.
    atomic_json(
        path,
        {
            "session_id": session["session_id"],
            "api": "http://127.0.0.1:8000",
            "started": True,
        },
    )
    assert runtime.config.product_key == KEY


def test_no_start_tools_are_installed_but_runtime_is_not_started(workspace):
    from installer.setup_runtime import SetupRuntime, binding_path
    from spx_mcp.errors import RuntimeAvailabilityError

    root, engine, session = workspace
    atomic_json(
        binding_path(engine, session["output"]),
        {
            "session_id": session["session_id"],
            "api": "http://127.0.0.1:8000",
            "started": False,
        },
    )
    with pytest.raises(RuntimeAvailabilityError) as error:
        SetupRuntime(root).create_client()
    assert error.value.code == "SPX_NOT_STARTED"
    assert (root / "spx.ps1").is_file() and (root / "spx.sh").is_file()


def test_no_start_update_keeps_active_binding_until_manual_start(
    workspace, tmp_path, monkeypatch
):
    from installer.setup_runtime import (
        SetupRuntime,
        binding_path,
        pending_binding_path,
        mark_runtime_started,
        publish_runtime,
    )

    root, engine, original = workspace
    active = binding_path(engine, original["output"])
    atomic_json(
        active,
        {
            "session_id": original["session_id"],
            "api": "http://127.0.0.1:8000",
            "started": True,
        },
    )
    replacement = engine.create(
        Path(original["output"]), "B" * 30, initial={"start": False}
    )
    monkeypatch.setattr(
        "installer.setup_runtime._endpoints",
        lambda _: {"api": "http://127.0.0.1:18000"},
    )
    publish_runtime(engine, replacement, started=False)
    pending = pending_binding_path(engine, original["output"])
    assert pending.is_file()
    assert SetupRuntime(root).config.product_key == KEY
    assert SetupRuntime(root).config.spx_base_url == "http://127.0.0.1:8000"

    descriptor = json.loads((root / "setup-session.json").read_text(encoding="utf-8"))
    descriptor["session_id"] = replacement["session_id"]
    atomic_json(root / "setup-session.json", descriptor)
    seed = Path(original["output"]) / ".env"
    seed.parent.mkdir(parents=True, exist_ok=True)
    seed.write_text("SPX_PRODUCT_KEY=" + "B" * 30, encoding="utf-8")
    assert mark_runtime_started(seed, root)
    assert not pending.exists()
    assert SetupRuntime(root).config.product_key == "B" * 30
    assert SetupRuntime(root).config.spx_base_url == "http://127.0.0.1:18000"


def test_failed_candidate_doctor_never_replaces_active_binding(workspace, monkeypatch):
    from installer.setup_runtime import binding_path, prepare_tools
    from installer.setup_session import SetupError
    import subprocess

    root, engine, original = workspace
    active = binding_path(engine, original["output"])
    binding = {
        "session_id": original["session_id"],
        "api": "http://127.0.0.1:8000",
        "started": True,
    }
    atomic_json(active, binding)
    replacement = engine.create(
        Path(original["output"]), "B" * 30, initial={"start": True}
    )
    prepare_workspace(root, engine, replacement["session_id"], bootstrap=False)
    monkeypatch.setattr(
        "installer.setup_runtime.subprocess.run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            command, 1, '{"ok": false}', ""
        ),
    )
    with pytest.raises(SetupError, match="could not verify"):
        prepare_tools(
            engine,
            engine._read(replacement["session_id"]),
            started=True,
            bootstrap=False,
        )
    assert json.loads(active.read_text(encoding="utf-8")) == binding


def test_runtime_blocked_during_replacement_and_recovery(workspace):
    from installer.setup_runtime import SetupRuntime, binding_path
    from spx_mcp.errors import RuntimeAvailabilityError

    root, engine, session = workspace
    atomic_json(
        binding_path(engine, session["output"]),
        {
            "session_id": session["session_id"],
            "api": "http://127.0.0.1:8000",
            "started": True,
        },
    )
    current = engine._read(session["session_id"])
    current.update(status="APPLYING", job={"job_id": "job", "pid": os.getpid()})
    engine._write(current)
    atomic_json(
        engine.root / "active-installation.json",
        {"session_id": current["session_id"], "job_id": "job"},
    )
    runtime = SetupRuntime(root)
    for status in ("APPLYING", "RECOVERY_REQUIRED"):
        current["status"] = status
        engine._write(current)
        with pytest.raises(RuntimeAvailabilityError):
            runtime.create_client()


@pytest.mark.skipif(sys.version_info < (3, 10), reason="MCP SDK requires Python 3.10+")
def test_same_stdio_connection_works_after_install_and_key_rotation(
    workspace, monkeypatch
):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import threading
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client
    from installer.setup_runtime import binding_path

    root, engine, session = workspace
    accepted = {"key": KEY, "requests": 0}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            accepted["requests"] += 1
            ok = self.headers.get("Authorization") == "Bearer " + accepted["key"]
            self.send_response(200 if ok else 401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps(
                    {"name": "system", "children": []}
                    if ok
                    else {"detail": "Invalid license key"}
                ).encode()
            )

        def log_message(self, *args):
            pass

    api = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=api.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{api.server_port}"
    profile = json.loads((root / ".mcp.json").read_text(encoding="utf-8"))[
        "mcpServers"
    ]["spx"]
    parameters = StdioServerParameters(
        command=profile["command"],
        args=profile["args"],
        env={
            **os.environ,
            "SPX_PRODUCT_KEY": "stale-host-key",
            "SPX_BASE_URL": "http://invalid.invalid",
        },
    )

    async def check():
        async with stdio_client(parameters) as (reader, writer):
            async with ClientSession(reader, writer) as client:
                await client.initialize()

                async def call(name):
                    response = await client.call_tool(name, {})
                    text = response.content[0].text
                    assert KEY not in text and "B" * 30 not in text
                    return json.loads(text)

                before = await call("health")
                assert before["error"]["code"] == "SPX_NOT_READY"
                binding = binding_path(engine, session["output"])
                atomic_json(
                    binding,
                    {"session_id": session["session_id"], "api": url, "started": True},
                )
                assert (await call("health"))["ok"]
                assert (await call("server_list_instances"))["instances"] == []
                replacement = engine.create(
                    Path(session["output"]), "B" * 30, initial={"start": False}
                )
                accepted["key"] = "B" * 30
                atomic_json(
                    binding,
                    {
                        "session_id": replacement["session_id"],
                        "api": url,
                        "started": True,
                    },
                )
                assert (await call("health"))["ok"]
                assert accepted["requests"] >= 4

    try:
        asyncio.run(check())
    finally:
        api.shutdown()
        api.server_close()
        thread.join(timeout=5)


@pytest.mark.skipif(
    sys.version_info < (3, 10),
    reason="MCP dependencies require Python 3.10+; covered by required 3.12 job",
)
def test_common_preparation_creates_workspace_without_resetting_job(
    tmp_path, monkeypatch
):
    from installer.setup_runtime import (
        prepare_tools,
        binding_path,
        pending_binding_path,
    )

    engine = SetupEngine(tmp_path / "private")
    session = engine.create(tmp_path / "generated", KEY, initial={"start": False})
    root = tmp_path / "tools"
    private = engine._read(session["session_id"])
    private["workspace"] = str(root)
    engine._write(private)
    plan = engine.plan(session["session_id"])
    job = engine.apply(
        session["session_id"], plan["plan_id"], plan["revision"], launch=False
    )
    monkeypatch.setattr(
        engine,
        "_prepare_tools",
        lambda current, *, started: prepare_tools(
            engine, current, started=started, bootstrap=False
        ),
    )
    engine.run_job(session["session_id"], job["job_id"])
    final = engine.get(session["session_id"])
    assert final["status"] == "SUCCEEDED"
    assert final["job"]["job_id"] == job["job_id"]
    assert final["tools"]["ok"] is True
    assert final["tools"]["server_checked"] is False
    assert pending_binding_path(engine, session["output"]).is_file()
    assert not binding_path(engine, session["output"]).exists()
    for path in root.rglob("*"):
        if path.is_file():
            assert KEY.encode() not in path.read_bytes()


def test_manual_start_enables_no_start_workspace(workspace, tmp_path):
    from installer.setup_runtime import SetupRuntime, binding_path, mark_runtime_started

    root, engine, session = workspace
    output = Path(session["output"])
    output.mkdir()
    seed = output / ".env"
    seed.write_text("SPX_PRODUCT_KEY=" + KEY)
    path = binding_path(engine, output)
    atomic_json(
        path,
        {
            "session_id": session["session_id"],
            "api": "http://127.0.0.1:8000",
            "started": False,
        },
    )
    assert mark_runtime_started(seed, root)
    assert SetupRuntime(root)._binding()[0]["started"]


def test_migration_preserves_settings_and_moves_credentials_outside_workspace(tmp_path):
    root = tmp_path / "existing managed workspace"
    root.mkdir()
    (root / ".spx-mcp-workspace.json").write_text('{"workspace_kind":"managed"}')
    (root / ".env").write_text("SPX_PRODUCT_KEY=" + KEY + "\nKEEP_SETTING=1\n")
    (root / ".codex").mkdir()
    (root / ".codex/config.toml").write_text(
        '[mcp_servers.spx]\ncommand = "old"\n[mcp_servers.spx.env]\nSPX_PRODUCT_KEY = "'
        + KEY
        + '"\n'
    )
    (root / ".mcp.json").write_text(
        '{"extra":true,"mcpServers":{"other":{"command":"other"}}}'
    )
    engine = SetupEngine(tmp_path / "private")
    session = engine.create(tmp_path / "generated", KEY, initial={"start": False})
    prepare_workspace(
        root, engine, session["session_id"], bootstrap=False, preserve_session=True
    )
    assert (root / ".env").read_text() == "KEEP_SETTING=1\n"
    assert KEY not in (root / ".codex/config.toml").read_text(encoding="utf-8")
    assert "[mcp_servers.spx.env]" not in (root / ".codex/config.toml").read_text(
        encoding="utf-8"
    )
    profile = json.loads((root / ".mcp.json").read_text())
    assert (
        profile["extra"]
        and "other" in profile["mcpServers"]
        and "spx" in profile["mcpServers"]
    )
    assert engine._key(engine._read(session["session_id"])) == KEY


def test_repair_preserves_job_and_removes_old_setup_profiles(workspace):
    root, engine, session = workspace
    (root / ".codex/config.toml").write_text(
        '[mcp_servers.spx_setup]\ncommand = "old"\n[mcp_servers.spx_setup.env]\nSETTING = "old"\n[mcp_servers.other]\ncommand = "other"\n'
    )
    (root / ".mcp.json").write_text('{"mcpServers":{"spx_setup":{"command":"old"}}}')
    current = engine._read(session["session_id"])
    current.update(status="SUCCEEDED", job={"job_id": "finished"})
    engine._write(current)
    prepare_workspace(
        root, engine, session["session_id"], bootstrap=False, preserve_session=True
    )
    assert engine.get(session["session_id"])["job"]["job_id"] == "finished"
    assert "[mcp_servers.spx_setup]" in (root / ".codex/config.toml").read_text()
    assert 'SETTING = "old"' not in (root / ".codex/config.toml").read_text()
    assert "[mcp_servers.other]" in (root / ".codex/config.toml").read_text()
    assert (
        "spx_setup"
        in json.loads((root / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]
    )
    current["status"] = "RECOVERY_REQUIRED"
    engine._write(current)
    from installer.setup_session import SetupError

    with pytest.raises(SetupError, match="recovery"):
        prepare_workspace(
            root, engine, session["session_id"], bootstrap=False, preserve_session=True
        )


def test_failed_replacement_does_not_publish_candidate_binding(workspace, monkeypatch):
    from installer.setup_runtime import SetupRuntime, binding_path

    root, engine, session = workspace
    path = binding_path(engine, session["output"])
    original = {
        "session_id": session["session_id"],
        "api": "http://127.0.0.1:8000",
        "started": True,
    }
    atomic_json(path, original)
    replacement = engine.create(
        Path(session["output"]), "B" * 30, initial={"start": False}
    )
    plan = engine.plan(replacement["session_id"])
    job = engine.apply(
        replacement["session_id"], plan["plan_id"], plan["revision"], launch=False
    )
    monkeypatch.setattr(
        engine,
        "_prepare_tools",
        lambda *a, **k: pytest.fail("Failed deployment must not publish tools"),
    )
    engine.run_job(
        replacement["session_id"], job["job_id"], start_callback=lambda *a: False
    )
    assert engine.get(replacement["session_id"])["status"] == "FAILED"
    assert json.loads(path.read_text()) == original
    assert SetupRuntime(root).config.product_key == KEY


@pytest.mark.skipif(
    sys.version_info < (3, 10),
    reason="MCP dependencies require Python 3.10+; covered by required 3.12 job",
)
def test_runtime_cli_no_start_and_inventory(workspace, capsys):
    from installer.spx_cli import main
    from installer.setup_runtime import binding_path

    root, engine, session = workspace
    atomic_json(
        binding_path(engine, session["output"]),
        {
            "session_id": session["session_id"],
            "api": "http://127.0.0.1:8000",
            "started": False,
        },
    )
    assert main(["doctor", "--workspace-root", str(root)]) == 0
    assert json.loads(capsys.readouterr().out)["server_check"]["checked"] is False
    if sys.version_info >= (3, 10):
        assert main(["call", "health", "--workspace-root", str(root)]) == 1
        assert json.loads(capsys.readouterr().out)["error"]["code"] == "SPX_NOT_STARTED"


def test_fresh_pending_install_passes_local_doctor_but_blocks_live_calls(
    workspace, capsys
):
    from installer.spx_cli import main
    from installer.setup_runtime import pending_binding_path

    root, engine, session = workspace
    atomic_json(
        pending_binding_path(engine, session["output"]),
        {
            "session_id": session["session_id"],
            "api": "http://127.0.0.1:8000",
            "started": False,
        },
    )
    assert main(["doctor", "--workspace-root", str(root)]) == 0
    assert json.loads(capsys.readouterr().out)["ok"]
    assert main(["call", "health", "--workspace-root", str(root)]) == 1
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "SPX_NOT_STARTED"


def test_doctor_identifies_stale_project_local_codex_mcp(workspace, tmp_path):
    from installer.spx_cli import project_mcp_check

    root, _, _ = workspace
    project = tmp_path / "another checkout"
    (project / ".codex").mkdir(parents=True)
    (project / ".codex/config.toml").write_text(
        '[mcp_servers.spx]\ncommand = "python"\nargs = ["-m", "spx_mcp", "stdio", "--repo-root", "old-checkout"]\n',
        encoding="utf-8",
    )
    stale = project_mcp_check(project, root)
    assert not stale["ok"] and "spx" in stale["message"]
    current = project_mcp_check(root, root)
    assert current["ok"]
