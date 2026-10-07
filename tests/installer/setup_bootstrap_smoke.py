"""Native CI bootstrap check; no Docker, runtime API or licensed stack needed."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from installer.setup_session import SetupEngine
from installer.setup_workspace import prepare_workspace, read_descriptor


def main():
    root = Path(tempfile.mkdtemp(prefix="spx-setup-smoke-"))
    engine = SetupEngine(root / "private")
    # Format-only fixture: configuration generation is not server qualification.
    key = "AAAAA-AAAAA-AAAAA-AAAAA-AAAAA-AAAAA"
    session = engine.create(
        root / "generated",
        key,
        initial={
            "protocols": ["http"],
            "start": False,
            "requirements": {
                "description": "Generate a local HTTP testing environment",
                "catalog_scope": "selected",
                "protocols": ["http"],
                "required_services": [],
                "external_services": {},
                "remove_services": [],
                "unresolved": [],
                "decisions": {
                    "install_spx_ui": True,
                    "start": False,
                    "service_bind_addresses": {},
                    "port_mappings": {},
                    "replace_existing": False,
                },
            },
        },
    )
    workspace = prepare_workspace(
        root / "Workspace with spaces Łódź", engine, session["session_id"]
    )
    for name in (
        "AGENTS.md",
        "CLAUDE.md",
        "INSTALLATION.md",
        "setup-session.json",
        ".codex/config.toml",
        ".mcp.json",
        "opencode.jsonc",
    ):
        assert key not in (workspace / name).read_text(encoding="utf-8")
    descriptor = read_descriptor(workspace)
    profiles = json.loads((workspace / ".mcp.json").read_text(encoding="utf-8"))
    assert set(profiles["mcpServers"]) >= {"spx_setup", "spx"}
    for toolset in ("setup", "runtime"):
        doctor = subprocess.run(
            [
                descriptor["python"],
                str(workspace / "installer/setup_mcp.py"),
                "doctor",
                "--workspace-root",
                str(workspace),
                "--toolset",
                toolset,
            ],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=True,
        )
        report = json.loads(doctor.stdout)
        assert report["ok"] and report["purpose"] == toolset
    launcher = (
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(workspace / "setup-cli.ps1"),
        ]
        if os.name == "nt"
        else ["sh", str(workspace / "setup-cli.sh")]
    )

    def call(action, *args):
        result = subprocess.run(
            [*launcher, action, *args, "--json"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            check=True,
        )
        assert key not in result.stdout
        response = json.loads(result.stdout)
        assert response["ok"]
        return response["result"]

    plan = call("plan")
    assert plan["ready"] and not plan["start"]
    job = call(
        "apply", "--plan-id", plan["plan_id"], "--revision", str(plan["revision"])
    )
    assert (
        call("apply", "--plan-id", plan["plan_id"], "--revision", str(plan["revision"]))
        == job
    )
    for _ in range(60):
        current = call("status")
        if current["status"] in {"SUCCEEDED", "FAILED", "RECOVERY_REQUIRED"}:
            assert current["status"] == "SUCCEEDED", current["status"]
            break
        time.sleep(0.5)
    else:
        raise AssertionError("Independent Setup worker did not complete")
    assert (root / "generated/bundle.json").is_file()
    assert key in (root / "generated/.env").read_text(encoding="utf-8")
    assert current["tools"]["ok"], current.get("mcp_warning")
    runtime_launcher = (
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(workspace / "spx.ps1"),
        ]
        if os.name == "nt"
        else ["sh", str(workspace / "spx.sh")]
    )
    diagnostic = subprocess.run(
        [*runtime_launcher, "doctor", "--json"],
        capture_output=True,
        encoding="utf-8",
        check=True,
        timeout=30,
    )
    assert json.loads(diagnostic.stdout)["ok"]
    blocked = subprocess.run(
        [*runtime_launcher, "call", "health", "--json"],
        capture_output=True,
        encoding="utf-8",
        timeout=30,
    )
    assert blocked.returncode == 1
    assert json.loads(blocked.stdout)["error"]["code"] == "SPX_NOT_STARTED"
    assert key not in diagnostic.stdout + blocked.stdout
    print(
        json.dumps(
            {
                "ok": True,
                "bootstrap": True,
                "independent_job": True,
                "platform": sys.platform,
                "python": sys.version.split()[0],
                "stack_started": False,
            }
        )
    )


if __name__ == "__main__":
    main()
