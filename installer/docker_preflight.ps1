# SPDX-License-Identifier: MIT

function Invoke-DockerInfo {
    param([int]$TimeoutMilliseconds = 5000)

    return Invoke-NativeCapture `
        -Command "docker" `
        -ArgumentList @("info") `
        -TimeoutMilliseconds $TimeoutMilliseconds
}

function Get-DockerInfoDetail {
    param([Parameter(Mandatory = $true)]$Result)

    $lines = @(
        (($Result.StdErr + "`n" + $Result.StdOut) -split "`r?`n") |
            ForEach-Object { "$($_)".Trim() } |
            Where-Object { $_ -and $_ -notmatch "errors pretty printing info" }
    )
    return ($lines -join " ")
}

function Write-DockerInfoDetail {
    param([Parameter(Mandatory = $true)]$Result)

    $detail = Get-DockerInfoDetail -Result $Result
    if ($detail) {
        $firstLine = ($detail -split "`r?`n")[0]
        [Console]::Error.WriteLine("[spx-install] Docker detail: $firstLine")
    }
}

function Invoke-DockerPreflightSleep {
    param([int]$Milliseconds = 2000)

    if ($Milliseconds -gt 0) {
        Start-Sleep -Milliseconds $Milliseconds
    }
}

function New-DockerPreflightTimer {
    return [System.Diagnostics.Stopwatch]::StartNew()
}

function Get-DockerPreflightElapsedMilliseconds {
    param([Parameter(Mandatory = $true)]$Timer)

    return $Timer.ElapsedMilliseconds
}

function Get-DockerDesktopPlatform {
    if ([Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT) {
        return "Windows"
    }

    try {
        if ((& uname -s 2>$null).Trim() -eq "Darwin") {
            return "MacOS"
        }
    } catch {
        # Keep non-Windows, non-macOS PowerShell hosts on the existing path.
    }

    return "Other"
}

function Wait-DockerDaemon {
    param([int]$TimeoutSeconds = 60)

    $timer = New-DockerPreflightTimer
    $timeoutMilliseconds = [Math]::Max(0, $TimeoutSeconds * 1000)
    $result = $null

    # Probe every two seconds, bounding each docker CLI call and the total wait.
    while ((Get-DockerPreflightElapsedMilliseconds -Timer $timer) -lt $timeoutMilliseconds) {
        $probeStartedMilliseconds = Get-DockerPreflightElapsedMilliseconds -Timer $timer
        $remainingMilliseconds = $timeoutMilliseconds - $probeStartedMilliseconds
        $probeTimeoutMilliseconds = [Math]::Min(2000, $remainingMilliseconds)
        $result = Invoke-DockerInfo -TimeoutMilliseconds $probeTimeoutMilliseconds
        if ($result.ExitCode -eq 0) {
            return [PSCustomObject]@{ Connected = $true; Result = $result }
        }

        $elapsedMilliseconds = Get-DockerPreflightElapsedMilliseconds -Timer $timer
        $remainingMilliseconds = $timeoutMilliseconds - $elapsedMilliseconds
        if ($remainingMilliseconds -le 0) {
            break
        }

        $probeDurationMilliseconds = $elapsedMilliseconds - $probeStartedMilliseconds
        $sleepMilliseconds = [Math]::Min(
            [Math]::Max(0, 2000 - $probeDurationMilliseconds),
            $remainingMilliseconds
        )
        Invoke-DockerPreflightSleep -Milliseconds $sleepMilliseconds
    }

    if (-not $result) {
        $result = [PSCustomObject]@{
            ExitCode = 124
            StdOut = ""
            StdErr = "Docker info timed out after $TimeoutSeconds seconds."
        }
    }
    return [PSCustomObject]@{ Connected = $false; Result = $result }
}

function Start-DockerDesktop {
    $dockerCommand = Get-Command "docker" -ErrorAction SilentlyContinue
    if ($dockerCommand) {
        try {
            $desktopStart = Start-Process `
                -FilePath $dockerCommand.Source `
                -ArgumentList @("desktop", "start", "--detach") `
                -NoNewWindow `
                -PassThru `
                -ErrorAction Stop

            # The Desktop CLI can remain alive while Desktop initializes. Do not
            # let that prevent the bounded daemon checks below from starting.
            if (-not $desktopStart.WaitForExit(2000) -or $desktopStart.ExitCode -eq 0) {
                Write-Host "[spx-install] Requested Docker Desktop startup through the Docker CLI."
                return $true
            }

            Write-Host "[spx-install] Docker Desktop CLI startup returned exit code $($desktopStart.ExitCode)."
        } catch {
            [Console]::Error.WriteLine(
                "[spx-install] Could not start Docker Desktop through the Docker CLI: $($_.Exception.Message)"
            )
        }
    }

    if ((Get-DockerDesktopPlatform) -eq "MacOS") {
        $openResult = Invoke-NativeCapture -Command "open" -ArgumentList @("-a", "Docker")
        if ($openResult.ExitCode -eq 0) {
            Write-Host "[spx-install] Opened Docker Desktop. Waiting for its daemon..."
            return $true
        }
        Write-Host "[spx-install] Could not open Docker Desktop automatically."
        return $false
    }

    $candidatePaths = @()
    if ($env:ProgramFiles) {
        $candidatePaths += Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
    }
    if (${env:ProgramFiles(x86)}) {
        $candidatePaths += Join-Path ${env:ProgramFiles(x86)} "Docker\Docker\Docker Desktop.exe"
    }
    if ($env:LOCALAPPDATA) {
        $candidatePaths += Join-Path $env:LOCALAPPDATA "Programs\Docker\Docker Desktop.exe"
    }

    foreach ($candidate in $candidatePaths) {
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            continue
        }

        try {
            Start-Process -FilePath $candidate -ErrorAction Stop | Out-Null
            Write-Host "[spx-install] Started Docker Desktop. Waiting for its daemon..."
            return $true
        } catch {
            [Console]::Error.WriteLine(
                "[spx-install] Could not launch Docker Desktop from '$candidate': $($_.Exception.Message)"
            )
        }
    }

    Write-Host "[spx-install] Could not start Docker Desktop automatically."
    return $false
}

function Test-DockerPromptAvailable {
    try {
        return ($Host.Name -eq "ConsoleHost" -and -not [Console]::IsInputRedirected)
    } catch {
        return $false
    }
}

function Get-DockerRecoveryMessage {
    param([Parameter(Mandatory = $true)]$Result)

    $detail = Get-DockerInfoDetail -Result $Result
    if ($detail -match "manually paused") {
        return "[spx-install] Docker Desktop is paused or its daemon is unavailable. Unpause Docker Desktop, wait until it is ready, then retry."
    }

    return "[spx-install] Docker Desktop is not reachable. Install and start Docker Desktop, wait until it is ready, then retry."
}

function Check-Docker {
    Need-Command "docker"

    $dockerInfo = Invoke-DockerInfo
    if ($dockerInfo.ExitCode -ne 0) {
        $desktopPlatform = Get-DockerDesktopPlatform
        if ($desktopPlatform -eq "Other") {
            Write-DockerInfoDetail -Result $dockerInfo
            $detail = Get-DockerInfoDetail -Result $dockerInfo
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

        Write-DockerInfoDetail -Result $dockerInfo
        Write-Host "[spx-install] Docker daemon is not reachable. Attempting to start Docker Desktop..."
        $null = Start-DockerDesktop

        $waitResult = Wait-DockerDaemon
        $dockerInfo = $waitResult.Result

        while (-not $waitResult.Connected) {
            $recoveryMessage = Get-DockerRecoveryMessage -Result $dockerInfo
            if (-not (Test-DockerPromptAvailable)) {
                throw "$recoveryMessage Run SPX Setup again after Docker Desktop is ready."
            }

            Write-Host $recoveryMessage
            $choice = ([string](Read-Host "Press R to retry the Docker connection or Q to quit")).Trim().ToLowerInvariant()
            switch ($choice) {
                "r" {
                    Write-Host "[spx-install] Retrying the Docker connection for up to 60 seconds..."
                    $waitResult = Wait-DockerDaemon
                    $dockerInfo = $waitResult.Result
                    if (-not $waitResult.Connected) {
                        Write-DockerInfoDetail -Result $dockerInfo
                    }
                }
                "q" {
                    throw $recoveryMessage
                }
                default {
                    Write-Host "[spx-install] Enter R to retry or Q to quit."
                }
            }
        }
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
