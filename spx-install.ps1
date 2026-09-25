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
        [string[]]$ArgumentList = @(),
        [int]$TimeoutMilliseconds = 0
    )

    $stdoutPath = [System.IO.Path]::GetTempFileName()
    $stderrPath = [System.IO.Path]::GetTempFileName()

    try {
        $process = Start-Process `
            -FilePath $Command `
            -ArgumentList $ArgumentList `
            -NoNewWindow `
            -PassThru `
            -RedirectStandardOutput $stdoutPath `
            -RedirectStandardError $stderrPath

        $timedOut = $false
        if ($TimeoutMilliseconds -gt 0) {
            $timedOut = -not $process.WaitForExit($TimeoutMilliseconds)
            if ($timedOut) {
                try { $process.Kill() } catch { }
                try { $null = $process.WaitForExit(2000) } catch { }
            }
        } else {
            $process.WaitForExit()
        }

        $stdoutText = ""
        $stderrText = ""
        if (Test-Path $stdoutPath) {
            $stdoutText = Get-Content -Path $stdoutPath -Raw -ErrorAction SilentlyContinue
        }
        if (Test-Path $stderrPath) {
            $stderrText = Get-Content -Path $stderrPath -Raw -ErrorAction SilentlyContinue
        }

        if ($timedOut) {
            $exitCode = 124
            $stderrText = "$Command timed out after $TimeoutMilliseconds ms."
        } else {
            $exitCode = $process.ExitCode
        }

        return [PSCustomObject]@{
            ExitCode = $exitCode
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

$InstallerPythonBin = Resolve-Python
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
            & $InstallerPythonBin -c $checkCmd 2>$null | Out-Null
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
    & $InstallerPythonBin -m pip install --user @($packages)
    if ($LASTEXITCODE -ne 0) {
        throw "[spx-install] pip install failed"
    }

    foreach ($entry in $missing) {
        if (-not (Test-PythonModule $entry.Module)) {
            throw "[spx-install] Unable to import module '$($entry.Module)' even after pip install."
        }
    }
}

try {
    . (Join-Path $RepoDir "installer/docker_preflight.ps1")
    Need-Command $InstallerPythonBin
    $DockerCompose = Check-Docker
    Check-PythonModules

    Set-Location -Path $RepoDir

    if ($args.Count -eq 0) {
        $installerArgs = @("generate", "--output", "build/spx-generated")
    } else {
        $installerArgs = $args
    }

    Write-Host "[spx-install] Running installer CLI with redacted arguments."

    & $InstallerPythonBin -m installer @installerArgs
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
