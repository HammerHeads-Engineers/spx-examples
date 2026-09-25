# SPDX-License-Identifier: MIT

from __future__ import annotations

import os
from pathlib import Path
import select
import shutil
import signal
import subprocess
import time

import pytest

if os.name == "nt":
    pty = None
else:
    import pty


ROOT = Path(__file__).resolve().parents[2]
SHELL_HELPER = ROOT / "installer" / "docker_preflight.sh"
POWERSHELL_HELPER = ROOT / "installer" / "docker_preflight.ps1"
BASH = shutil.which("bash") if os.name != "nt" else None
POWERSHELL = shutil.which("pwsh") or shutil.which("powershell")


def _bash_harness(
    *, ready_after: int, start_status: int = 0, platform: str = "Darwin"
) -> str:
    helper = str(SHELL_HELPER).replace("'", "'\\''")
    return f"""
source '{helper}'
need_cmd() {{ :; }}
uname() {{ printf '%s\\n' '{platform}'; }}
sleep() {{ :; }}
info_calls=0
start_calls=0
open_calls=0
READY_AFTER={ready_after}
START_STATUS={start_status}
docker() {{
  case "${{1:-}}" in
    info)
      info_calls=$((info_calls + 1))
      if (( info_calls >= READY_AFTER )); then return 0; fi
      printf '%s\\n' 'cannot connect to docker API' >&2
      return 1
      ;;
    desktop)
      start_calls=$((start_calls + 1))
      return "$START_STATUS"
      ;;
    compose)
      return 0
      ;;
  esac
  return 1
}}
open() {{
  open_calls=$((open_calls + 1))
  return 0
}}
check_docker
status=$?
printf 'RESULT=%s INFO_CALLS=%s START_CALLS=%s OPEN_CALLS=%s\\n' \\
  "$status" "$info_calls" "$start_calls" "$open_calls"
exit "$status"
"""


def _run_bash(script: str, *, input_text: str = "") -> subprocess.CompletedProcess[str]:
    assert BASH is not None
    return subprocess.run(
        [BASH, "-c", script],
        input=input_text,
        capture_output=True,
        text=True,
        check=False,
    )


def _run_bash_with_tty(
    script: str, input_text: str
) -> subprocess.CompletedProcess[str]:
    assert BASH is not None
    assert pty is not None
    master_fd, slave_fd = pty.openpty()
    process = subprocess.Popen(
        [BASH, "-c", script],
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        close_fds=True,
        start_new_session=True,
    )
    os.close(slave_fd)
    output = bytearray()
    deadline = time.monotonic() + 10
    prompt = b"Press R to retry the Docker connection or Q to quit:"

    try:
        while time.monotonic() < deadline and prompt not in output:
            ready, _, _ = select.select([master_fd], [], [], 0.1)
            if not ready:
                continue
            try:
                output.extend(os.read(master_fd, 4096))
            except OSError:
                break

        if prompt not in output:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
            pytest.fail("Docker preflight did not reach its retry prompt.")

        os.write(master_fd, input_text.encode())
        post_input_deadline = time.monotonic() + 10
        while process.poll() is None and time.monotonic() < post_input_deadline:
            ready, _, _ = select.select([master_fd], [], [], 0.1)
            if not ready:
                continue
            try:
                output.extend(os.read(master_fd, 4096))
            except OSError:
                break
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
        returncode = process.wait(timeout=5)
    finally:
        os.close(master_fd)

    return subprocess.CompletedProcess(
        [BASH, "-c", script],
        returncode,
        stdout=output.decode(errors="replace"),
        stderr="",
    )


@pytest.mark.skipif(BASH is None or os.name == "nt", reason="Requires POSIX Bash")
def test_macos_docker_preflight_accepts_daemon_that_is_already_ready() -> None:
    result = _run_bash(_bash_harness(ready_after=1))

    assert result.returncode == 0
    assert "RESULT=0" in result.stdout
    assert "START_CALLS=0" in result.stdout


@pytest.mark.skipif(BASH is None or os.name == "nt", reason="Requires POSIX Bash")
def test_macos_docker_preflight_starts_desktop_and_waits_for_daemon() -> None:
    result = _run_bash(_bash_harness(ready_after=2))

    assert result.returncode == 0
    assert "START_CALLS=1" in result.stdout
    assert "OPEN_CALLS=0" in result.stdout


@pytest.mark.skipif(BASH is None or os.name == "nt", reason="Requires POSIX Bash")
def test_macos_docker_preflight_falls_back_to_opening_docker_app() -> None:
    result = _run_bash(_bash_harness(ready_after=2, start_status=1))

    assert result.returncode == 0
    assert "START_CALLS=1" in result.stdout
    assert "OPEN_CALLS=1" in result.stdout


@pytest.mark.skipif(BASH is None or os.name == "nt", reason="Requires a POSIX TTY")
def test_macos_docker_preflight_retries_after_user_starts_desktop() -> None:
    result = _run_bash_with_tty(_bash_harness(ready_after=34), "R\n")

    assert result.returncode == 0
    assert "Retrying the Docker connection" in result.stdout
    assert "RESULT=0" in result.stdout


@pytest.mark.skipif(BASH is None or os.name == "nt", reason="Requires a POSIX TTY")
def test_macos_docker_preflight_quits_after_failed_retry() -> None:
    result = _run_bash_with_tty(_bash_harness(ready_after=1000), "Q\n")

    assert result.returncode == 1
    assert "Install and start Docker Desktop" in result.stdout
    assert "RESULT=1" in result.stdout


@pytest.mark.skipif(BASH is None or os.name == "nt", reason="Requires POSIX Bash")
def test_macos_docker_preflight_noninteractive_failure_does_not_prompt() -> None:
    result = _run_bash(_bash_harness(ready_after=1000))

    assert result.returncode == 1
    assert "Install and start Docker Desktop" in result.stderr
    assert "Run SPX Setup again" in result.stderr
    assert "Press R to retry" not in result.stderr


@pytest.mark.skipif(BASH is None or os.name == "nt", reason="Requires POSIX Bash")
def test_linux_docker_preflight_keeps_existing_failure_behavior() -> None:
    result = _run_bash(_bash_harness(ready_after=1000, platform="Linux"))

    assert result.returncode == 1
    assert (
        "Docker daemon not reachable. Start Docker Desktop/service and retry."
        in result.stderr
    )
    assert "START_CALLS=0" in result.stdout


def _powershell_script(body: str) -> str:
    helper = str(POWERSHELL_HELPER).replace("'", "''")
    return f". '{helper}'\n{body}"


def _run_powershell(body: str) -> subprocess.CompletedProcess[str]:
    assert POWERSHELL is not None
    return subprocess.run(
        [
            POWERSHELL,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            _powershell_script(body),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


_POWERSHELL_MOCKS = r"""
$ErrorActionPreference = 'Stop'
$script:infoCalls = 0
$script:readyAfter = READY_AFTER_PLACEHOLDER
$script:startCalls = 0
$script:promptChoice = 'Q'
$script:fakeElapsedMilliseconds = 0
function Need-Command { param([string]$Command) }
function Invoke-NativeCapture {
  param([string]$Command, [string[]]$ArgumentList = @(), [int]$TimeoutMilliseconds = 0)
  if ($ArgumentList.Count -eq 1 -and $ArgumentList[0] -eq 'info') {
    $script:infoCalls++
    if ($script:infoCalls -ge $script:readyAfter) {
      return [PSCustomObject]@{ ExitCode = 0; StdOut = ''; StdErr = '' }
    }
    return [PSCustomObject]@{ ExitCode = 1; StdOut = ''; StdErr = 'cannot connect to docker API' }
  }
  if ($ArgumentList.Count -ge 2 -and $ArgumentList[0] -eq 'compose') {
    return [PSCustomObject]@{ ExitCode = 0; StdOut = 'compose'; StdErr = '' }
  }
  return [PSCustomObject]@{ ExitCode = 1; StdOut = ''; StdErr = 'unsupported command' }
}
function Invoke-DockerPreflightSleep {
  param([int]$Milliseconds = 2000)
  $script:fakeElapsedMilliseconds += $Milliseconds
}
function New-DockerPreflightTimer {
  $script:fakeElapsedMilliseconds = 0
  return [PSCustomObject]@{}
}
function Get-DockerPreflightElapsedMilliseconds { param($Timer); return $script:fakeElapsedMilliseconds }
function Start-DockerDesktop { $script:startCalls++; return $true }
function Get-DockerDesktopPlatform { return 'Windows' }
function Test-DockerPromptAvailable { return $true }
function Read-Host { param([string]$Prompt); return $script:promptChoice }
"""


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is not available")
def test_windows_docker_preflight_accepts_daemon_that_is_already_ready() -> None:
    mocks = _POWERSHELL_MOCKS.replace("READY_AFTER_PLACEHOLDER", "1")
    body = (
        mocks
        + "\n$result = Check-Docker\n"
        + "if ($result -ne 'docker compose' -or $script:startCalls -ne 0) { throw 'unexpected result' }\n"
        + "'PREFLIGHT_TEST_PASSED'\n"
    )
    result = _run_powershell(body)

    assert result.returncode == 0, result.stderr
    assert "PREFLIGHT_TEST_PASSED" in result.stdout


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is not available")
def test_windows_docker_preflight_starts_desktop_and_waits_for_daemon() -> None:
    mocks = _POWERSHELL_MOCKS.replace("READY_AFTER_PLACEHOLDER", "2")
    body = (
        mocks
        + "\n$result = Check-Docker\n"
        + "if ($result -ne 'docker compose' -or $script:startCalls -ne 1) { throw 'unexpected result' }\n"
        + "'PREFLIGHT_TEST_PASSED'\n"
    )
    result = _run_powershell(body)

    assert result.returncode == 0, result.stderr
    assert "PREFLIGHT_TEST_PASSED" in result.stdout


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is not available")
def test_windows_docker_preflight_retries_after_user_starts_desktop() -> None:
    mocks = _POWERSHELL_MOCKS.replace("READY_AFTER_PLACEHOLDER", "33").replace(
        "$script:promptChoice = 'Q'", "$script:promptChoice = 'R'"
    )
    body = (
        mocks
        + "\n$result = Check-Docker\n"
        + "if ($result -ne 'docker compose' -or $script:startCalls -ne 1) { throw 'unexpected result' }\n"
        + "'PREFLIGHT_TEST_PASSED'\n"
    )
    result = _run_powershell(body)

    assert result.returncode == 0, result.stderr
    assert "Retrying the Docker connection" in result.stdout
    assert "PREFLIGHT_TEST_PASSED" in result.stdout


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is not available")
def test_windows_docker_preflight_quits_with_actionable_error() -> None:
    mocks = _POWERSHELL_MOCKS.replace("READY_AFTER_PLACEHOLDER", "1000")
    body = (
        mocks
        + "\ntry { Check-Docker | Out-Null; throw 'expected failure' } catch {"
        + " if ($_.Exception.Message -notmatch 'Install and start Docker Desktop') { throw };"
        + " 'PREFLIGHT_TEST_PASSED' }\n"
    )
    result = _run_powershell(body)

    assert result.returncode == 0, result.stderr
    assert "PREFLIGHT_TEST_PASSED" in result.stdout


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is not available")
def test_windows_docker_preflight_uses_docker_desktop_cli_when_available() -> None:
    body = r"""
$ErrorActionPreference = 'Stop'
$script:capturedArguments = ''
function Start-Process {
  [CmdletBinding()]
  param([string]$FilePath, [string[]]$ArgumentList = @(), [switch]$NoNewWindow, [switch]$PassThru)
  $script:capturedArguments = $ArgumentList -join ' '
  $process = [PSCustomObject]@{ ExitCode = 0; WaitTimeoutMs = 0 }
  $script:process = $process
  $process | Add-Member -MemberType ScriptMethod -Name WaitForExit -Value {
    param([int]$TimeoutMs)
    $this.WaitTimeoutMs = $TimeoutMs
    return $false
  }
  return $process
}
if (-not (Start-DockerDesktop)) { throw 'desktop was not started' }
if ($script:capturedArguments -ne 'desktop start --detach') { throw 'unexpected start command' }
if ($script:process.WaitTimeoutMs -ne 2000) { throw 'startup command was not bounded' }
'PREFLIGHT_TEST_PASSED'
"""
    result = _run_powershell(body)

    assert result.returncode == 0, result.stderr
    assert "PREFLIGHT_TEST_PASSED" in result.stdout


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is not available")
def test_windows_docker_preflight_bounds_blocked_info_probes_and_total_wait() -> None:
    body = r"""
$ErrorActionPreference = 'Stop'
$script:fakeElapsedMilliseconds = 0
$script:probeTimeouts = @()
function New-DockerPreflightTimer { return [PSCustomObject]@{} }
function Get-DockerPreflightElapsedMilliseconds { param($Timer); return $script:fakeElapsedMilliseconds }
function Invoke-DockerPreflightSleep {
  param([int]$Milliseconds = 2000)
  $script:fakeElapsedMilliseconds += $Milliseconds
}
function Invoke-DockerInfo {
  param([int]$TimeoutMilliseconds = 5000)
  $script:probeTimeouts += $TimeoutMilliseconds
  $script:fakeElapsedMilliseconds += $TimeoutMilliseconds
  return [PSCustomObject]@{ ExitCode = 124; StdOut = ''; StdErr = 'docker info timed out' }
}
$result = Wait-DockerDaemon -TimeoutSeconds 5
if ($result.Connected) { throw 'unexpected connection' }
if ($script:fakeElapsedMilliseconds -ne 5000) { throw 'wait exceeded its deadline' }
if ($script:probeTimeouts.Count -ne 3) { throw 'unexpected number of probes' }
if ($script:probeTimeouts[-1] -ne 1000) { throw 'last probe exceeded remaining time' }
'PREFLIGHT_TEST_PASSED'
"""
    result = _run_powershell(body)

    assert result.returncode == 0, result.stderr
    assert "PREFLIGHT_TEST_PASSED" in result.stdout


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is not available")
def test_windows_docker_preflight_noninteractive_failure_does_not_prompt() -> None:
    mocks = _POWERSHELL_MOCKS.replace("READY_AFTER_PLACEHOLDER", "1000").replace(
        "function Test-DockerPromptAvailable { return $true }",
        "function Test-DockerPromptAvailable { return $false }",
    )
    body = (
        mocks
        + "\ntry { Check-Docker | Out-Null; throw 'expected failure' } catch {"
        + " if ($_.Exception.Message -notmatch 'Run SPX Setup again') { throw };"
        + " 'PREFLIGHT_TEST_PASSED' }\n"
    )
    result = _run_powershell(body)

    assert result.returncode == 0, result.stderr
    assert "PREFLIGHT_TEST_PASSED" in result.stdout


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is not available")
def test_non_desktop_powershell_hosts_keep_existing_daemon_failure_behavior() -> None:
    mocks = _POWERSHELL_MOCKS.replace("READY_AFTER_PLACEHOLDER", "1000").replace(
        "function Get-DockerDesktopPlatform { return 'Windows' }",
        "function Get-DockerDesktopPlatform { return 'Other' }",
    )
    body = (
        mocks
        + "\ntry { Check-Docker | Out-Null; throw 'expected failure' } catch {"
        + " if ($_.Exception.Message -notmatch 'Start or unpause Docker Desktop/service') { throw };"
        + " if ($script:startCalls -ne 0) { throw 'unexpected desktop start' };"
        + " 'PREFLIGHT_TEST_PASSED' }\n"
    )
    result = _run_powershell(body)

    assert result.returncode == 0, result.stderr
    assert "PREFLIGHT_TEST_PASSED" in result.stdout


@pytest.mark.skipif(
    POWERSHELL is None or os.name != "nt", reason="Windows-only launcher fallback"
)
def test_windows_docker_preflight_launches_installed_desktop_when_cli_start_is_unavailable(
    tmp_path: Path,
) -> None:
    expected_path = tmp_path / "Docker" / "Docker" / "Docker Desktop.exe"
    expected_path.parent.mkdir(parents=True)
    expected_path.touch()
    root = str(tmp_path).replace("'", "''")
    body = f"""
$ErrorActionPreference = 'Stop'
$env:ProgramFiles = '{root}'
$script:startedPath = ''
function Invoke-NativeCapture {{
  param([string]$Command, [string[]]$ArgumentList = @(), [int]$TimeoutMilliseconds = 0)
  return [PSCustomObject]@{{ ExitCode = 1; StdOut = ''; StdErr = 'unsupported command' }}
}}
function Start-Process {{
  [CmdletBinding()]
  param([string]$FilePath, [string[]]$ArgumentList = @(), [switch]$NoNewWindow, [switch]$PassThru)
  if ($ArgumentList -contains 'desktop') {{ throw 'CLI startup unavailable' }}
  $script:startedPath = $FilePath
}}
if (-not (Start-DockerDesktop)) {{ throw 'desktop was not started' }}
if ($script:startedPath -ne '{str(expected_path).replace("'", "''")}') {{ throw 'unexpected desktop path' }}
'PREFLIGHT_TEST_PASSED'
"""
    result = _run_powershell(body)

    assert result.returncode == 0, result.stderr
    assert "PREFLIGHT_TEST_PASSED" in result.stdout
