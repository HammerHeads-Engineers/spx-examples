# SPDX-License-Identifier: MIT
"""Exercise the generated Windows transaction orchestration with failed stages."""

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from installer import stack_runner as sr
from installer import mcp_workspace as mw


def test_bootstrap_does_not_inherit_launcher_tls_keylog(tmp_path, monkeypatch):
    for name in ("stack_manager.py", "docker-compose.generated.yml", ".env",
                 "docker-compose.transaction.yml", "network.py", "modbus_port_configurator.py",
                 "runtime_bootstrap.py", "bootstrap_runner.py", "product_key.py"):
        (tmp_path / name).write_text("__TRANSACTION_TOKEN__", encoding="utf-8")
    (tmp_path / "bundle.json").write_text(json.dumps({"installation_id": "install"}))
    monkeypatch.setenv("SSLKEYLOGFILE", str(tmp_path))
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example:3128")
    checked = []

    def run(argv, **kwargs):
        if Path(str(argv[1])).name == "runtime_bootstrap.py":
            env = kwargs["env"]
            assert bool("SSLKEYLOGFILE" not in env), "Launcher keylog must not reach bootstrap"
            assert env["HTTPS_PROXY"] == "http://proxy.example:3128"
            assert env["PYTHONIOENCODING"] == "utf-8"
            checked.append(True)
            return subprocess.CompletedProcess(argv, 1, b"", b"")
        assert argv[0] != "docker", "Runtime failure must precede stack replacement"
        return subprocess.CompletedProcess(argv, 0, b"", b"")

    monkeypatch.setattr(sr.subprocess, "run", run)
    monkeypatch.setattr(sr.shutil, "which", lambda name: name)
    assert sr._start(tmp_path, assume_yes=True) == 1
    assert checked == [True]
    assert sr.os.environ["SSLKEYLOGFILE"] == str(tmp_path)


@pytest.mark.parametrize(
    "failure_stage", ["compose", "healthcheck", "bootstrap", "commit"]
)
@pytest.mark.parametrize("rollback_fails", [False, True])
def test_failure_captures_diagnostics_before_rollback_and_retains_recovery_files(
    tmp_path, monkeypatch, capsys, failure_stage, rollback_fails
):
    files = (
        "stack_manager.py",
        "docker-compose.generated.yml",
        ".env",
        "docker-compose.transaction.yml",
        "network.py",
        "modbus_port_configurator.py",
        "runtime_bootstrap.py",
        "bootstrap_runner.py",
        "product_key.py",
    )
    for name in files:
        (tmp_path / name).write_text("__TRANSACTION_TOKEN__", encoding="utf-8")
    (tmp_path / "bundle.json").write_text(json.dumps({"installation_id": "install"}))
    snapshot = tmp_path / ".spx-stack-snapshot.json"
    calls = []

    def run(argv, **kwargs):
        args = [str(arg) for arg in argv]
        calls.append(args)
        name = Path(args[1]).name
        stdout = b""
        code = 0
        if name == "runtime_bootstrap.py":
            stdout = sys.executable.encode()
        elif name == "modbus_port_configurator.py" and args[2].startswith("required-"):
            stdout = b"8000"
        elif name == "stack_manager.py":
            command = args[2]
            if command == "prepare":
                snapshot.write_text("old stack snapshot")
            elif command == "diagnose":
                path = Path(args[args.index("--diagnostics-path") + 1])
                path.parent.mkdir()
                path.write_text("failure evidence")
            elif command == "rollback":
                code = int(rollback_fails)
                if not rollback_fails:
                    snapshot.unlink()
            elif command == "wait-health" and failure_stage == "healthcheck":
                code = 1
            elif command == "commit" and failure_stage == "commit":
                code = 1
        elif name == "bootstrap_runner.py" and failure_stage == "bootstrap":
            code = 1
        elif args[0] == "docker":
            stdout = b"transaction-current-spx-server\n"
            if "up" in args and failure_stage == "compose":
                code = 1
        return subprocess.CompletedProcess(argv, code, stdout, b"")

    monkeypatch.setattr(sr.subprocess, "run", run)
    monkeypatch.setattr(sr.shutil, "which", lambda name: name)
    monkeypatch.setattr(sr.uuid, "uuid4", lambda: SimpleNamespace(hex="current"))
    monkeypatch.delenv("SPX_BASE_URL", raising=False)
    sync_calls = []
    monkeypatch.setattr(mw, "synchronize_managed_workspace", lambda *args: sync_calls.append(args))
    assert sr._start(tmp_path, assume_yes=True) == 1
    assert not sync_calls, "Uncommitted installations and rollback must preserve MCP settings"
    manager_calls = [args for args in calls if Path(args[1]).name == "stack_manager.py"]
    assert [args[2] for args in manager_calls][-2:] == ["diagnose", "rollback"]
    for args in manager_calls[-2:]:
        assert args[args.index("--transaction-token") + 1] == "current"
    diagnose, rollback = manager_calls[-2:]
    assert diagnose[diagnose.index("--failure-stage") + 1] == failure_stage
    assert rollback[rollback.index("--api-url") + 1] == "http://127.0.0.1:8000"
    assert (tmp_path / "logs" / "start-current.json").read_text() == "failure evidence"
    assert snapshot.exists() == rollback_fails
    assert (
        tmp_path / ".docker-compose.transaction.current.yml"
    ).exists() == rollback_fails
    output = capsys.readouterr().err
    assert "Failure diagnostics:" in output
    if rollback_fails:
        assert "automatic restore was not completed" in output
        assert "Recovery snapshot retained" in output and "SPX Setup" in output


@pytest.mark.parametrize("mcp_fails", [False, True])
@pytest.mark.parametrize("setup_transaction", [False, True])
def test_managed_sync_happens_only_after_commit_and_does_not_roll_back_healthy_stack(
    tmp_path, monkeypatch, capsys, mcp_fails, setup_transaction
):
    for name in ("stack_manager.py", "docker-compose.generated.yml", ".env",
                 "docker-compose.transaction.yml", "network.py", "modbus_port_configurator.py",
                 "runtime_bootstrap.py", "bootstrap_runner.py", "product_key.py"):
        (tmp_path / name).write_text("__TRANSACTION_TOKEN__", encoding="utf-8")
    (tmp_path / "bundle.json").write_text(json.dumps({"installation_id": "install"}))
    commands = []
    sync_calls = []

    def run(argv, **kwargs):
        args = [str(arg) for arg in argv]
        commands.append(args)
        name = Path(args[1]).name
        stdout = b""
        if name == "runtime_bootstrap.py":
            stdout = sys.executable.encode()
        elif name == "modbus_port_configurator.py" and args[2].startswith("required-"):
            stdout = b"8000"
        elif args[0] == "docker":
            stdout = b"transaction-current-spx-server\n"
        return subprocess.CompletedProcess(argv, 0, stdout, b"")

    def sync(seed):
        sync_calls.append(seed)
        assert seed == tmp_path / ".env"
        assert any(Path(args[1]).name == "stack_manager.py" and args[2] == "commit" for args in commands)
        if mcp_fails:
            raise OSError("private-product-key-must-not-be-logged")
        return True

    monkeypatch.setattr(sr.subprocess, "run", run)
    monkeypatch.setattr(sr.shutil, "which", lambda name: name)
    monkeypatch.setattr(sr.uuid, "uuid4", lambda: SimpleNamespace(hex="current"))
    monkeypatch.setattr(mw, "synchronize_managed_workspace", sync)
    monkeypatch.delenv("SPX_BASE_URL", raising=False)
    if setup_transaction:
        monkeypatch.setenv("SPX_SETUP_JOURNAL", str(tmp_path / "journal.json"))
    else:
        monkeypatch.delenv("SPX_SETUP_JOURNAL", raising=False)
    assert sr._start(tmp_path, assume_yes=True) == 0
    assert not any(Path(args[1]).name == "stack_manager.py" and args[2] == "rollback" for args in commands)
    output = capsys.readouterr()
    if setup_transaction:
        assert not sync_calls, "SetupEngine publishes its binding after verification"
        assert "configuration refreshed" not in output.out
    elif mcp_fails:
        assert "stack is healthy" in output.err
        assert "SPX MCP Setup" in output.err
    else:
        assert "configuration refreshed" in output.out
    assert "private-product-key-must-not-be-logged" not in output.err + output.out
