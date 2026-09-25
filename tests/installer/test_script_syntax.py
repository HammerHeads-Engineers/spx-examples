# SPDX-License-Identifier: MIT

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Optional

import pytest


def _find_working_bash() -> Optional[str]:
    bash = shutil.which("bash")
    if bash is None:
        return None
    try:
        result = subprocess.run(
            [bash, "-c", "exit 0"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return bash if result.returncode == 0 else None


BASH = _find_working_bash()


@pytest.mark.skipif(shutil.which("pwsh") is None, reason="PowerShell is not available")
def test_power_shell_installer_entrypoint_parses() -> None:
    scripts = (
        Path(__file__).parents[2] / "spx-install.ps1",
        Path(__file__).parents[2] / "installer" / "docker_preflight.ps1",
    )
    for script in scripts:
        result = subprocess.run(
            [
                "pwsh",
                "-NoProfile",
                "-Command",
                (
                    "$errors=@(); [System.Management.Automation.Language.Parser]::ParseFile("
                    f"'{script}', [ref]$null, [ref]$errors) | Out-Null; "
                    "if ($errors.Count -gt 0) { exit 1 }"
                ),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr


@pytest.mark.skipif(BASH is None, reason="Bash is not available")
def test_shell_installer_entrypoint_parses() -> None:
    scripts = (
        Path(__file__).parents[2] / "spx-install.sh",
        Path(__file__).parents[2] / "installer" / "docker_preflight.sh",
    )
    for script in scripts:
        result = subprocess.run(
            [BASH, "-n", str(script)], check=False, capture_output=True, text=True
        )
        assert result.returncode == 0, result.stderr
