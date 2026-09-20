# SPDX-License-Identifier: MIT

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(shutil.which("pwsh") is None, reason="PowerShell is not available")
def test_power_shell_installer_entrypoint_parses() -> None:
    script = Path(__file__).parents[2] / "spx-install.ps1"
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


def test_shell_installer_entrypoint_parses() -> None:
    script = Path(__file__).parents[2] / "spx-install.sh"
    result = subprocess.run(["bash", "-n", str(script)], check=False, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
