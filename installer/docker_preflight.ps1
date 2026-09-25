# SPDX-License-Identifier: MIT

$script:DockerCliPath = $null

function Get-DockerDesktopPlatform {
    if ([Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT) {
        return "Windows"
    }

    try {
        $platform = (& uname -s 2>$null).Trim()
        if ($platform -eq "Darwin") { return "macOS" }
        if ($platform -eq "Linux") { return "Linux" }
    } catch {
        # Keep unsupported PowerShell hosts on the manual-recovery path.
    }

    return "Other"
}

function Resolve-DockerCli {
    $command = Get-Command "docker" -ErrorAction SilentlyContinue
    if ($command) {
        if ($command.Source) {
            $script:DockerCliPath = $command.Source
        } elseif ($command.Path) {
            $script:DockerCliPath = $command.Path
        } else {
            $script:DockerCliPath = "docker"
        }
        return $true
    }

    $candidates = @("$HOME\.docker\bin\docker.exe", "$HOME\.docker\bin\docker")
    if ($env:ProgramFiles) {
        $candidates += Join-Path $env:ProgramFiles "Docker\Docker\resources\bin\docker.exe"
    }
    if (${env:ProgramFiles(x86)}) {
        $candidates += Join-Path ${env:ProgramFiles(x86)} "Docker\Docker\resources\bin\docker.exe"
    }
    if ($env:LOCALAPPDATA) {
        $candidates += Join-Path $env:LOCALAPPDATA "Docker\resources\bin\docker.exe"
        $candidates += Join-Path $env:LOCALAPPDATA "Programs\Docker\Docker\resources\bin\docker.exe"
    }
    $candidates += @(
        "/Applications/Docker.app/Contents/Resources/bin/docker",
        "/opt/homebrew/bin/docker",
        "/usr/local/bin/docker",
        "/usr/bin/docker",
        "/snap/bin/docker"
    )

    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            $script:DockerCliPath = $candidate
            return $true
        }
    }

    $script:DockerCliPath = $null
    return $false
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
        $startParameters = @{
            FilePath = $Command
            ArgumentList = $ArgumentList
            NoNewWindow = $true
            PassThru = $true
            RedirectStandardOutput = $stdoutPath
            RedirectStandardError = $stderrPath
            ErrorAction = "Stop"
        }
        $process = Start-Process @startParameters

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

        $stdoutText = if (Test-Path $stdoutPath) { Get-Content $stdoutPath -Raw -ErrorAction SilentlyContinue } else { "" }
        $stderrText = if (Test-Path $stderrPath) { Get-Content $stderrPath -Raw -ErrorAction SilentlyContinue } else { "" }

        if ($timedOut) {
            $exitCode = 124
            $stderrText = "$Command timed out after $TimeoutMilliseconds ms."
        } else {
            $exitCode = $process.ExitCode
        }

        return [PSCustomObject]@{
            ExitCode = $exitCode
            StdOut = [string]$stdoutText
            StdErr = [string]$stderrText
        }
    } catch {
        return [PSCustomObject]@{
            ExitCode = 127
            StdOut = ""
            StdErr = $_.Exception.Message
        }
    } finally {
        Remove-Item $stdoutPath, $stderrPath -Force -ErrorAction SilentlyContinue
    }
}

function Invoke-DockerInfo {
    param([int]$TimeoutMilliseconds = 5000)

    if (-not $script:DockerCliPath -and -not (Resolve-DockerCli)) {
        return [PSCustomObject]@{ ExitCode = 127; StdOut = ""; StdErr = "Docker CLI was not found." }
    }
    return Invoke-NativeCapture -Command $script:DockerCliPath -ArgumentList @("info") -TimeoutMilliseconds $TimeoutMilliseconds
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
        [Console]::Error.WriteLine("[spx-install] Docker detail: $detail")
    }
}

function Invoke-DockerPreflightSleep {
    param([int]$Milliseconds = 2000)
    if ($Milliseconds -gt 0) { Start-Sleep -Milliseconds $Milliseconds }
}

function New-DockerPreflightTimer {
    return [System.Diagnostics.Stopwatch]::StartNew()
}

function Get-DockerPreflightElapsedMilliseconds {
    param([Parameter(Mandatory = $true)]$Timer)
    return $Timer.ElapsedMilliseconds
}

function Wait-DockerDaemon {
    param([int]$TimeoutSeconds = 60)

    $timer = New-DockerPreflightTimer
    $timeoutMilliseconds = [Math]::Max(0, $TimeoutSeconds * 1000)
    $result = $null

    while ((Get-DockerPreflightElapsedMilliseconds -Timer $timer) -lt $timeoutMilliseconds) {
        $probeStartedMilliseconds = Get-DockerPreflightElapsedMilliseconds -Timer $timer
        $remainingMilliseconds = $timeoutMilliseconds - $probeStartedMilliseconds
        $probeTimeoutMilliseconds = [Math]::Min(2000, $remainingMilliseconds)
        if (Resolve-DockerCli) {
            $result = Invoke-DockerInfo -TimeoutMilliseconds $probeTimeoutMilliseconds
            if ($result.ExitCode -eq 0) {
                return [PSCustomObject]@{ Connected = $true; Result = $result }
            }
        } else {
            $result = [PSCustomObject]@{ ExitCode = 127; StdOut = ""; StdErr = "Docker CLI was not found." }
        }

        $elapsedMilliseconds = Get-DockerPreflightElapsedMilliseconds -Timer $timer
        $remainingMilliseconds = $timeoutMilliseconds - $elapsedMilliseconds
        if ($remainingMilliseconds -le 0) { break }

        $probeDurationMilliseconds = $elapsedMilliseconds - $probeStartedMilliseconds
        $sleepMilliseconds = [Math]::Min(
            [Math]::Max(0, 2000 - $probeDurationMilliseconds),
            $remainingMilliseconds
        )
        Invoke-DockerPreflightSleep -Milliseconds $sleepMilliseconds
    }

    if (-not $result) {
        $result = [PSCustomObject]@{ ExitCode = 124; StdOut = ""; StdErr = "Docker info timed out after $TimeoutSeconds seconds." }
    }
    return [PSCustomObject]@{ Connected = $false; Result = $result }
}

function Start-DockerDesktop {
    $platform = Get-DockerDesktopPlatform
    if (Resolve-DockerCli) {
        try {
            $process = Start-Process `
                -FilePath $script:DockerCliPath `
                -ArgumentList @("desktop", "start", "--detach") `
                -NoNewWindow `
                -PassThru `
                -ErrorAction Stop
            if (-not $process.WaitForExit(2000) -or $process.ExitCode -eq 0) {
                Write-Host "[spx-install] Requested Docker Desktop startup through the Docker CLI."
                return $true
            }
        } catch {
            # A missing or older Docker Desktop CLI may not provide this command.
        }
    }

    if ($platform -eq "macOS") {
        $openResult = Invoke-NativeCapture -Command "open" -ArgumentList @("-a", "Docker") -TimeoutMilliseconds 5000
        if ($openResult.ExitCode -eq 0) {
            Write-Host "[spx-install] Opened Docker Desktop. Waiting for Docker Engine..."
            return $true
        }
        Write-Host "[spx-install] Docker Desktop could not be opened automatically."
        return $false
    }

    if ($platform -eq "Windows") {
        $candidatePaths = @()
        if ($env:ProgramFiles) { $candidatePaths += Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe" }
        if (${env:ProgramFiles(x86)}) { $candidatePaths += Join-Path ${env:ProgramFiles(x86)} "Docker\Docker\Docker Desktop.exe" }
        if ($env:LOCALAPPDATA) { $candidatePaths += Join-Path $env:LOCALAPPDATA "Programs\Docker\Docker\Docker Desktop.exe" }

        foreach ($candidate in $candidatePaths) {
            if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
            try {
                Start-Process -FilePath $candidate -ErrorAction Stop | Out-Null
                Write-Host "[spx-install] Started Docker Desktop. Waiting for Docker Engine..."
                return $true
            } catch {
                [Console]::Error.WriteLine("[spx-install] Could not launch Docker Desktop: $($_.Exception.Message)")
            }
        }
    }

    Write-Host "[spx-install] Docker Desktop could not be started automatically."
    return $false
}

function Resolve-DockerCompose {
    if (-not $script:DockerCliPath -and -not (Resolve-DockerCli)) { return $null }

    $plugin = Invoke-NativeCapture -Command $script:DockerCliPath -ArgumentList @("compose", "version") -TimeoutMilliseconds 5000
    if ($plugin.ExitCode -eq 0) { return "docker compose" }

    $legacy = Get-Command "docker-compose" -ErrorAction SilentlyContinue
    if ($legacy) { return "docker-compose" }
    foreach ($candidate in @("/usr/local/bin/docker-compose", "/usr/bin/docker-compose", "$HOME\.docker\bin\docker-compose.exe")) {
        if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) { return $candidate }
    }
    return $null
}

function Test-DockerState {
    if (-not (Resolve-DockerCli)) {
        return [PSCustomObject]@{ Ready = $false; Failure = "cli"; Result = $null; Compose = $null }
    }

    $info = Invoke-DockerInfo
    if ($info.ExitCode -ne 0) {
        return [PSCustomObject]@{ Ready = $false; Failure = "daemon"; Result = $info; Compose = $null }
    }

    $compose = Resolve-DockerCompose
    if (-not $compose) {
        return [PSCustomObject]@{ Ready = $false; Failure = "compose"; Result = $info; Compose = $null }
    }
    return [PSCustomObject]@{ Ready = $true; Failure = ""; Result = $info; Compose = $compose }
}

function Test-DockerPromptAvailable {
    try { return ($Host.Name -eq "ConsoleHost" -and -not [Console]::IsInputRedirected) }
    catch { return $false }
}

function Write-DockerRecoveryInstructions {
    param([string]$Failure, [string]$Platform, $Result)

    $detail = if ($Result) { Get-DockerInfoDetail -Result $Result } else { "" }
    if ($Failure -eq "compose") {
        if ($Platform -eq "Linux") {
            [Console]::Error.WriteLine("Docker Compose is not available.")
            [Console]::Error.WriteLine("Install the Docker Compose plugin using https://docs.docker.com/compose/install/linux/.")
        } else {
            [Console]::Error.WriteLine("Docker Compose is not available.")
            [Console]::Error.WriteLine("Install or update Docker Desktop from https://www.docker.com/products/docker-desktop/.")
            [Console]::Error.WriteLine("Docker Desktop includes the Docker Compose plugin.")
        }
        return
    }

    if ($Failure -eq "cli" -and $Platform -eq "Linux") {
        [Console]::Error.WriteLine("Docker CLI is not installed or was not found.")
        [Console]::Error.WriteLine("Install Docker Engine and the Docker Compose plugin using https://docs.docker.com/engine/install/.")
        [Console]::Error.WriteLine("On systemd-based Linux distributions, you can start the service with: sudo systemctl start docker")
        return
    }

    if ($Failure -eq "cli") {
        [Console]::Error.WriteLine("Docker CLI was not found.")
        [Console]::Error.WriteLine("If Docker Desktop is not installed, install it from https://www.docker.com/products/docker-desktop/.")
        [Console]::Error.WriteLine("Then open Docker Desktop and wait until Docker Engine is running.")
        return
    }

    if ($Failure -eq "daemon" -and $detail -match "(?i)permission denied") {
        [Console]::Error.WriteLine("Docker CLI is installed, but this account cannot access Docker Engine.")
        if ($Platform -eq "Linux") {
            [Console]::Error.WriteLine("Follow Docker's instructions for non-root access: https://docs.docker.com/engine/install/linux-postinstall/.")
            [Console]::Error.WriteLine("Then sign out and back in before retrying.")
        } else {
            [Console]::Error.WriteLine("Check that Docker Desktop is running under this account. If access is still denied, ask your administrator to check permissions.")
        }
        return
    }

    if ($Platform -eq "Windows" -or $Platform -eq "macOS") {
        [Console]::Error.WriteLine("Docker Engine is not reachable. Docker Desktop may still be starting or paused.")
        [Console]::Error.WriteLine("Open Docker Desktop, unpause it if needed, and wait until Docker Engine is running.")
        [Console]::Error.WriteLine("If Docker Desktop is not installed, install it from https://www.docker.com/products/docker-desktop/.")
        return
    }

    [Console]::Error.WriteLine("Docker Engine is not available.")
    [Console]::Error.WriteLine("Install and start Docker Engine, then follow https://docs.docker.com/engine/install/.")
    [Console]::Error.WriteLine("On systemd-based Linux distributions, you can start the service with: sudo systemctl start docker")
}

function Start-DockerRecoveryAttempt {
    param([string]$Failure, [string]$Platform)

    if (($Platform -eq "Windows" -or $Platform -eq "macOS") -and ($Failure -eq "cli" -or $Failure -eq "daemon")) {
        Write-Host "[spx-install] Docker is not ready. Attempting to start Docker Desktop..."
        $started = Start-DockerDesktop
        if ($started -or $Failure -eq "daemon") {
            $wait = Wait-DockerDaemon -TimeoutSeconds 60
            if (-not $wait.Connected) { Write-DockerInfoDetail -Result $wait.Result }
        }
    } elseif ($Platform -eq "Linux" -and $Failure -eq "daemon") {
        Write-Host "[spx-install] Checking Docker Engine for up to 60 seconds..."
        $wait = Wait-DockerDaemon -TimeoutSeconds 60
        if (-not $wait.Connected) { Write-DockerInfoDetail -Result $wait.Result }
    }
}

function Check-Docker {
    $platform = Get-DockerDesktopPlatform
    $state = Test-DockerState
    if ($state.Ready) { return $state.Compose }

    if ($platform -ne "Linux") {
        Start-DockerRecoveryAttempt -Failure $state.Failure -Platform $platform
    }
    $state = Test-DockerState
    if ($state.Ready) { return $state.Compose }

    while ($true) {
        Write-DockerRecoveryInstructions -Failure $state.Failure -Platform $platform -Result $state.Result
        if (-not (Test-DockerPromptAvailable)) {
            $rerunHint = if ($platform -eq "Linux") {
                "Run SPX Setup again after Docker Engine and Docker Compose are ready."
            } else {
                "Run SPX Setup again after Docker Desktop and Docker Compose are ready."
            }
            throw "$rerunHint"
        }

        $choice = ([string](Read-Host "Press Enter to retry Docker checks (wait up to 60 seconds), or type Q to quit:")).Trim()
        if ($choice -match "(?i)^q$") {
            throw "[spx-install] Docker preflight cancelled by the user."
        }
        if ($choice) {
            [Console]::Error.WriteLine("[spx-install] Press Enter to retry Docker checks (wait up to 60 seconds), or type Q to quit.")
            continue
        }

        Write-Host "[spx-install] Retrying Docker CLI, Engine, and Compose checks..."
        if ($state.Failure -eq "cli" -or $state.Failure -eq "daemon") {
            Write-Host "[spx-install] Waiting up to 60 seconds for Docker Engine..."
            $wait = Wait-DockerDaemon -TimeoutSeconds 60
            if (-not $wait.Connected) { Write-DockerInfoDetail -Result $wait.Result }
        }
        $state = Test-DockerState
        if ($state.Ready) { return $state.Compose }
    }
}

function Test-DockerPreflightRequired {
    param([string[]]$Arguments = @())

    if ($Arguments -contains "-h" -or $Arguments -contains "--help") { return $false }
    if ($Arguments.Count -eq 0) { return $true }
    if ($Arguments[0] -ne "generate") { return $false }

    $hasSelector = $false
    $hasStart = $false
    $hasNoStart = $false
    foreach ($argument in $Arguments | Select-Object -Skip 1) {
        if ($argument -in @("--packages", "--profile-ids", "--protocols") -or
            $argument -match "^--(packages|profile-ids|protocols)=") { $hasSelector = $true }
        if ($argument -eq "--start") { $hasStart = $true }
        if ($argument -eq "--no-start") { $hasNoStart = $true }
    }

    if ($hasStart) { return $true }
    if ($hasNoStart -or $hasSelector) { return $false }
    return $true
}
