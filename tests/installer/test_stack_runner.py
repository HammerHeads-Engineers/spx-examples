# SPDX-License-Identifier: MIT
"""Exercise the generated Windows transaction orchestration with failed stages."""

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from installer import stack_runner as sr


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
    assert sr._start(tmp_path, assume_yes=True) == 1
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
