#!/usr/bin/env pwsh
# SPDX-License-Identifier: MIT
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepoDir = Split-Path -Parent $MyInvocation.MyCommand.Path

function Exit-WithMessage {
    param(
        [string]$Message,
        [int]$ExitCode = 1
    )

    [Console]::Error.WriteLine($Message)
    exit $ExitCode
}

function Invoke-NativeCapture {
    param(
        [string]$Command,
        [string[]]$ArgumentList = @()
    )

    $stdoutPath = [System.IO.Path]::GetTempFileName()
    $stderrPath = [System.IO.Path]::GetTempFileName()

    try {
        $process = Start-Process `
            -FilePath $Command `
            -ArgumentList $ArgumentList `
            -NoNewWindow `
            -Wait `
            -PassThru `
            -RedirectStandardOutput $stdoutPath `
            -RedirectStandardError $stderrPath

        $stdoutText = ""
        $stderrText = ""
        if (Test-Path $stdoutPath) {
            $stdoutText = Get-Content -Path $stdoutPath -Raw -ErrorAction SilentlyContinue
        }
        if (Test-Path $stderrPath) {
            $stderrText = Get-Content -Path $stderrPath -Raw -ErrorAction SilentlyContinue
        }

        return [PSCustomObject]@{
            ExitCode = $process.ExitCode
            StdOut = $stdoutText
            StdErr = $stderrText
        }
    } finally {
        Remove-Item $stdoutPath, $stderrPath -Force -ErrorAction SilentlyContinue
    }
}

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
    & $PythonBin -m pip install --user @($packages)
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
    $dockerInfo = Invoke-NativeCapture -Command "docker" -ArgumentList @("info")
    if ($dockerInfo.ExitCode -ne 0) {
        $dockerInfoLines = @(
            (($dockerInfo.StdErr + "`n" + $dockerInfo.StdOut) -split "`r?`n") | ForEach-Object { "$_".Trim() } | Where-Object {
            $_ -and $_ -notmatch "errors pretty printing info"
            }
        )
        if ($dockerInfoLines.Count -gt 0) {
            [Console]::Error.WriteLine("[spx-install] Docker detail: $($dockerInfoLines[0])")
        }
        $detail = ($dockerInfoLines -join " ")
        if ($detail -match "manually paused") {
            throw "[spx-install] Docker Desktop is paused. Open Docker Desktop and unpause it, then retry."
        }
        if (
            $detail -match "failed to connect to the docker api" -or
            $detail -match "daemon is running" -or
            $detail -match "dockerdesktoplinuxengine" -or
            $detail -match "the system cannot find the file specified"
        ) {
            throw "[spx-install] Docker Desktop or the Docker daemon is not running. Start Docker Desktop, wait until it is fully started, and retry."
        }
        throw "[spx-install] Docker daemon not reachable. Start or unpause Docker Desktop/service and retry."
    }

    $dockerComposeVersion = Invoke-NativeCapture -Command "docker" -ArgumentList @("compose", "version")
    if ($dockerComposeVersion.ExitCode -eq 0) {
        return "docker compose"
    }

    if (Get-Command docker-compose -ErrorAction SilentlyContinue) {
        return "docker-compose"
    }

    throw "[spx-install] Neither 'docker compose' nor 'docker-compose' is available."
}

try {
    Need-Command $PythonBin
    $DockerCompose = Check-Docker
    Check-PythonModules

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
} catch {
    $message = $_.Exception.Message
    if (-not $message) {
        $message = "[spx-install] Installation failed."
    }
    Exit-WithMessage $message 1
}
