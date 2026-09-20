# SPDX-License-Identifier: MIT
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$bootstrap = Join-Path $PSScriptRoot "codex_mcp_bootstrap.py"

if (Get-Command py -ErrorAction SilentlyContinue) {
    $pythonCommand = "py"
    $pythonArgs = @("-3")
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonCommand = "python"
    $pythonArgs = @()
} else {
    throw "Python launcher not found. Install Python or use 'py'."
}

$scriptArgs = @($bootstrap, "--repo-root", $repoRoot) + $args
& $pythonCommand @pythonArgs @scriptArgs
exit $LASTEXITCODE
