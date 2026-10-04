# SPDX-License-Identifier: MIT
"""Run the Windows prerequisite pip path without executing the wizard."""

from pathlib import Path
import shutil
import subprocess
import sys

import pytest


@pytest.mark.parametrize("pip_fails", [False, True])
def test_prerequisite_pip_ignores_tls_keylog_and_restores_environment(tmp_path, pip_fails):
    shell = shutil.which("powershell") or shutil.which("pwsh")
    if shell is None:
        pytest.skip("Windows prerequisite entrypoint requires PowerShell")
    installer = Path(__file__).parents[2] / "spx-install.ps1"
    body = r"""
$ErrorActionPreference = 'Stop'
$tokens = $null; $parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($args[0], [ref]$tokens, [ref]$parseErrors)
$fn = $ast.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Check-PythonModules'}, $true)
Invoke-Expression $fn.Extent.Text
$script:probePython = $args[1]
$script:pipFails = $args[2] -eq 'True'
$script:installed = $false
$Env:SSLKEYLOGFILE = $args[3]
$originalKeylog = $Env:SSLKEYLOGFILE
$RequiredModules = @(@{Module='yaml'; Package='pyyaml'})
$InstallerPythonBin = 'Invoke-TestPython'
function Invoke-TestPython {
    if ($args[0] -eq '-c') {
        $global:LASTEXITCODE = [int](-not $script:installed)
        return
    }
    & $script:probePython -c 'import ssl; c=ssl.create_default_context(); assert c.verify_mode==ssl.CERT_REQUIRED and c.check_hostname'
    if ($LASTEXITCODE -ne 0) { throw 'Prerequisite pip inherited inaccessible TLS keylog' }
    $script:installed = $true
    $global:LASTEXITCODE = [int]$script:pipFails
}
$caught = $false
try { Check-PythonModules } catch {
    if ($_.Exception.Message -ne '[spx-install] pip install failed') { throw }
    $caught = $true
}
if ($caught -ne $script:pipFails) { throw 'Unexpected pip failure handling' }
if ($Env:SSLKEYLOGFILE -ne $originalKeylog) { throw 'Parent TLS keylog changed' }
Write-Output 'PASS'
"""
    script = tmp_path / "probe.ps1"
    script.write_text(body, encoding="utf-8")
    result = subprocess.run(
        [shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
         str(installer), sys.executable, str(pip_fails), str(tmp_path)],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "PASS" in result.stdout
