# SPDX-License-Identifier: MIT
"""Tests for installer.runtime_bootstrap."""

from __future__ import annotations

import json
import os
from pathlib import Path

from installer import runtime_bootstrap
from installer import mcp_workspace
import pytest


@pytest.mark.parametrize(
    "runner", [runtime_bootstrap.run_command, mcp_workspace.run_command]
)
def test_runtime_children_ignore_inaccessible_tls_keylog_without_changing_parent(
    tmp_path: Path, monkeypatch, runner
) -> None:
    # A directory is an invalid keylog file on every supported platform. This
    # reproduces the GUI launcher's inaccessible virtual-file path without TLS
    # traffic, package downloads or changing the host environment.
    monkeypatch.setenv("SSLKEYLOGFILE", str(tmp_path))
    monkeypatch.setenv("SPX_BOOTSTRAP_ENV_PROBE", "preserved")
    for name in ("PIP_CERT", "REQUESTS_CA_BUNDLE", "HTTPS_PROXY"):
        monkeypatch.setenv(name, "preserved-test-setting")
    runner(
        [
            runtime_bootstrap.sys.executable,
            "-c",
            "import os, ssl; "
            "context = ssl.create_default_context(); "
            "assert context.verify_mode == ssl.CERT_REQUIRED; "
            "assert context.check_hostname; "
            "assert 'SSLKEYLOGFILE' not in os.environ; "
            "assert all(os.environ[k] == 'preserved-test-setting' for k in "
            "('PIP_CERT', 'REQUESTS_CA_BUNDLE', 'HTTPS_PROXY')); "
            "assert os.environ['SPX_BOOTSTRAP_ENV_PROBE'] == 'preserved'",
        ]
    )
    assert os.environ["SSLKEYLOGFILE"] == str(tmp_path)


def test_is_healthy_virtualenv_rejects_missing_pyvenv_cfg(tmp_path: Path) -> None:
    venv_dir = tmp_path / ".venv"
    (venv_dir / "bin").mkdir(parents=True)
    (venv_dir / "bin" / "python").write_text("", encoding="utf-8")

    assert runtime_bootstrap.is_healthy_virtualenv(venv_dir) is False


def test_ensure_runtime_recreates_broken_virtualenv(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        runtime_bootstrap, "ensure_secure_environment", lambda python: None
    )
    venv_dir = tmp_path / ".venv"
    python_path = runtime_bootstrap.venv_python_path(venv_dir)
    python_path.parent.mkdir(parents=True)
    python_path.write_text("", encoding="utf-8")
    stale_path = venv_dir / "stale.txt"
    stale_path.write_text("stale", encoding="utf-8")

    calls: list[list[str]] = []

    def fake_run_command(argv: list[str]) -> None:
        calls.append(argv)
        assert argv == [runtime_bootstrap.sys.executable, "-m", "venv", str(venv_dir)]
        python_path.parent.mkdir(parents=True, exist_ok=True)
        python_path.write_text("#!/usr/bin/env python\n", encoding="utf-8")
        (venv_dir / "pyvenv.cfg").write_text("home = /tmp/python\n", encoding="utf-8")

    monkeypatch.setattr(runtime_bootstrap, "run_command", fake_run_command)
    monkeypatch.setattr(
        runtime_bootstrap,
        "is_healthy_virtualenv",
        lambda candidate: (candidate / "pyvenv.cfg").exists(),
    )

    python_bin = runtime_bootstrap.ensure_runtime(venv_dir, [])

    assert calls == [[runtime_bootstrap.sys.executable, "-m", "venv", str(venv_dir)]]
    assert python_bin == python_path
    assert stale_path.exists() is False
    assert (venv_dir / "pyvenv.cfg").exists() is True
    assert json.loads((venv_dir / ".spx-runtime.json").read_text(encoding="utf-8")) == {
        "packages": [],
        "python_executable": str(Path(runtime_bootstrap.sys.executable).resolve()),
        "python_version": runtime_bootstrap.sys.version,
    }


def test_ensure_runtime_reuses_healthy_virtualenv_without_recreate(
    tmp_path: Path,
    monkeypatch,
) -> None:
    venv_dir = tmp_path / ".venv"
    python_path = runtime_bootstrap.venv_python_path(venv_dir)
    python_path.parent.mkdir(parents=True)
    python_path.write_text("#!/usr/bin/env python\n", encoding="utf-8")
    (venv_dir / "pyvenv.cfg").write_text("home = /tmp/python\n", encoding="utf-8")
    (venv_dir / ".spx-runtime.json").write_text(
        json.dumps(
            {
                "packages": [],
                "python_executable": str(
                    Path(runtime_bootstrap.sys.executable).resolve()
                ),
                "python_version": runtime_bootstrap.sys.version,
            }
        ),
        encoding="utf-8",
    )

    calls: list[list[str]] = []

    monkeypatch.setattr(
        runtime_bootstrap, "run_command", lambda argv: calls.append(argv)
    )
    monkeypatch.setattr(
        runtime_bootstrap, "is_healthy_virtualenv", lambda candidate: True
    )
    secured = []
    monkeypatch.setattr(runtime_bootstrap, "ensure_secure_environment", secured.append)

    python_bin = runtime_bootstrap.ensure_runtime(venv_dir, [])

    assert python_bin == python_path
    assert calls == []
    assert secured == [python_path]


@pytest.mark.parametrize(
    "version,expected",
    [
        (None, False),
        ("26.2.1", False),
        ("26.2.2rc1", False),
        ("26.2.2", True),
        ("26.2.2.0", True),
        ("26.10", True),
    ],
)
def test_pip_version_gate(version, expected):
    assert runtime_bootstrap.safe_version(version, "26.2.2") is expected


@pytest.mark.parametrize("pip_present", [True, False])
def test_security_bootstrap_precedes_other_network_installs(monkeypatch, pip_present):
    versions = {"python": [3, 12, 10], "certifi": "2025.8.3", "uv": "0.13.3"}
    if pip_present:
        versions["pip"] = "25.0"
    calls = []

    def run(argv):
        calls.append(argv)
        if "ensurepip" in argv:
            versions["pip"] = "25.0"
        elif runtime_bootstrap.PIP_BOOTSTRAP in argv:
            assert "--no-index" in argv and "--no-deps" in argv
            assert "#sha256=" in argv[-1]
            versions["pip"] = "26.2.2"
        else:
            assert versions["pip"] == "26.2.2"
            versions.update(certifi="2026.10.23", uv="0.13.4")

    monkeypatch.setattr(
        runtime_bootstrap, "environment_versions", lambda python: versions.copy()
    )
    monkeypatch.setattr(runtime_bootstrap, "has_module", lambda *args: pip_present)
    monkeypatch.setattr(runtime_bootstrap, "run_command", run)
    runtime_bootstrap.ensure_secure_environment(Path("target-python"))
    installs = [argv for argv in calls if "install" in argv]
    assert runtime_bootstrap.PIP_BOOTSTRAP in installs[0]
    assert "certifi>=2026.10.19" in installs[1]
    assert "uv>=0.13.4" in installs[1]
    assert all(argv[0] == "target-python" for argv in calls)


def test_unsupported_python_stops_before_network(monkeypatch):
    monkeypatch.setattr(
        runtime_bootstrap, "environment_versions", lambda python: {"python": [3, 9, 19]}
    )
    monkeypatch.setattr(
        runtime_bootstrap,
        "run_command",
        lambda argv: pytest.fail("Unexpected installation"),
    )
    with pytest.raises(RuntimeError, match="Python 3.10"):
        runtime_bootstrap.ensure_pip_available(Path("old-python"))


def test_failed_bootstrap_stops_before_certifi_install(monkeypatch):
    monkeypatch.setattr(
        runtime_bootstrap,
        "environment_versions",
        lambda python: {"python": [3, 12], "pip": "25.0"},
    )
    monkeypatch.setattr(runtime_bootstrap, "has_module", lambda *args: True)
    calls = []
    monkeypatch.setattr(runtime_bootstrap, "run_command", calls.append)
    with pytest.raises(RuntimeError, match="safe pip"):
        runtime_bootstrap.ensure_secure_environment(Path("target-python"))
    assert len(calls) == 1
    assert runtime_bootstrap.PIP_BOOTSTRAP in calls[0]


def test_current_environment_needs_no_network_and_does_not_install_uv(monkeypatch):
    monkeypatch.setattr(
        runtime_bootstrap,
        "environment_versions",
        lambda python: {"python": [3, 12], "pip": "26.2.2", "certifi": "2026.10.23"},
    )
    monkeypatch.setattr(
        runtime_bootstrap,
        "run_command",
        lambda argv: pytest.fail("Unexpected installation"),
    )
    runtime_bootstrap.ensure_secure_environment(Path("target-python"))


def test_windows_python_payload_hash_is_checked_before_use(tmp_path):
    import hashlib
    import shutil
    import subprocess

    shell = shutil.which("powershell") or shutil.which("pwsh")
    if not shell:
        pytest.skip("PowerShell is unavailable")
    payload = tmp_path / "python.exe"
    payload.write_bytes(b"test installer payload")
    digest = hashlib.sha256(payload.read_bytes()).hexdigest()
    build_script = Path(__file__).parents[2] / "packaging/windows/Build.ps1"
    probe = tmp_path / "check.ps1"
    probe.write_text(
        r"""
$tokens = $null; $errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($args[0], [ref]$tokens, [ref]$errors)
$fn = $ast.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Assert-PythonInstallerHash'}, $true)
Invoke-Expression $fn.Extent.Text
$PythonInstallerSha256 = $args[2]
Assert-PythonInstallerHash -Path $args[1]
$PythonInstallerSha256 = '0' * 64
try { Assert-PythonInstallerHash -Path $args[1] } catch {
  if ($_.Exception.Message -like '*SHA-256 mismatch*') { exit 0 }
  throw
}
throw 'Unverified installer payload was accepted'
""",
        encoding="utf-8",
    )
    subprocess.run(
        [
            shell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(probe),
            str(build_script),
            str(payload),
            digest,
        ],
        check=True,
    )
