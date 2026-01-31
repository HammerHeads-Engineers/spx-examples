#!/usr/bin/env pwsh
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepoDir = Split-Path -Parent $MyInvocation.MyCommand.Path

function Resolve-Python {
    function Test-PythonCommand {
        param([string]$Command)
        try {
            & $Command -c "import sys" 2>$null | Out-Null
            return ($LASTEXITCODE -eq 0)
        } catch {
            return $false
        }
    }

    if ($Env:PYTHON_BIN) {
        if (Test-PythonCommand $Env:PYTHON_BIN) {
            return $Env:PYTHON_BIN
        }
        throw "[spx-install] PYTHON_BIN is set to '$Env:PYTHON_BIN' but is not a working Python interpreter."
    }

    foreach ($candidate in @("python3", "python")) {
        if (Get-Command $candidate -ErrorAction SilentlyContinue) {
            if (Test-PythonCommand $candidate) {
                return $candidate
            }
        }
    }

    throw "[spx-install] Missing required command: python (3.x). Install Python 3 or set PYTHON_BIN."
}

$PythonBin = Resolve-Python
$RequiredModules = @(
    @{ Module = "yaml"; Package = "pyyaml" },
    @{ Module = "colorama"; Package = "colorama" }
)

function Need-Command {
    param([string]$Command)
    if (-not (Get-Command $Command -ErrorAction SilentlyContinue)) {
        throw "[spx-install] Missing required command: $Command"
    }
}

function Check-PythonModules {
    function Test-PythonModule {
        param([string]$Module)
        $checkCmd = "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('$Module') else 1)"
        try {
            & $PythonBin -c $checkCmd 2>$null | Out-Null
        } catch {
            return $false
        }
        return ($LASTEXITCODE -eq 0)
    }

    $missing = @()
    foreach ($entry in $RequiredModules) {
        if (-not (Test-PythonModule $entry.Module)) {
            $missing += $entry
        }
    }
    if ($missing.Count -eq 0) {
        return
    }

    $moduleNames = $missing | ForEach-Object { $_.Module }
    $packages = $missing | ForEach-Object { $_.Package }
    Write-Host "[spx-install] Missing Python modules: $($moduleNames -join ', '). Installing via pip..."
    & $PythonBin -m pip install --user @packages
    if ($LASTEXITCODE -ne 0) {
        throw "[spx-install] pip install failed"
    }

    foreach ($entry in $missing) {
        if (-not (Test-PythonModule $entry.Module)) {
            throw "[spx-install] Unable to import module '$($entry.Module)' even after pip install."
        }
    }
}

function Check-Docker {
    Need-Command "docker"
    docker info | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "[spx-install] Docker daemon not reachable. Start Docker Desktop/service and retry."
    }

    & docker compose version | Out-Null
    if ($LASTEXITCODE -eq 0) {
        return "docker compose"
    }

    if (Get-Command docker-compose -ErrorAction SilentlyContinue) {
        return "docker-compose"
    }

    throw "[spx-install] Neither 'docker compose' nor 'docker-compose' is available."
}

Need-Command $PythonBin
Check-PythonModules
$DockerCompose = Check-Docker

Set-Location -Path $RepoDir

if ($args.Count -eq 0) {
    $installerArgs = @("generate", "--output", "build/spx-generated")
} else {
    $installerArgs = $args
}

$argsDisplay = $installerArgs -join ' '
Write-Host "[spx-install] Running installer CLI: $PythonBin -m installer $argsDisplay"

& $PythonBin -m installer @installerArgs
if ($LASTEXITCODE -ne 0) {
    throw "[spx-install] Installer CLI failed with exit code $LASTEXITCODE"
}
