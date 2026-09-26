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
WINDOWS_POWERSHELL = shutil.which("powershell") if os.name == "nt" else None


def _bash_harness(
    *,
    platform: str = "macOS",
    cli_present: bool = True,
    ready_after: int = 1,
    compose_present: bool = True,
    start_status: int = 0,
    cli_marker: str = "",
    compose_marker: str = "",
) -> str:
    helper = str(SHELL_HELPER).replace("'", "'\\''")
    marker_test = f'[[ -f "{cli_marker}" ]]' if cli_marker else "false"
    compose_test = f'[[ -f "{compose_marker}" ]]' if compose_marker else "false"
    return f"""
source '{helper}'
PLATFORM='{platform}'
CLI_PRESENT={1 if cli_present else 0}
READY_AFTER={ready_after}
COMPOSE_PRESENT={1 if compose_present else 0}
START_STATUS={start_status}
info_calls=0
start_calls=0
sleep_calls=0
spx_docker_platform() {{ printf '%s\\n' "$PLATFORM"; }}
spx_resolve_docker_cli() {{ (( CLI_PRESENT == 1 )) || {marker_test}; }}
spx_start_docker_desktop() {{ start_calls=$((start_calls + 1)); return "$START_STATUS"; }}
sleep() {{ sleep_calls=$((sleep_calls + 1)); :; }}
docker() {{
  case "${{1:-}}" in
    info)
      info_calls=$((info_calls + 1))
      if (( info_calls >= READY_AFTER )); then return 0; fi
      printf '%s\\n' 'cannot connect to docker API' >&2
      return 1
      ;;
    desktop) return "$START_STATUS" ;;
    compose)
      if (( COMPOSE_PRESENT == 1 )) || {compose_test}; then return 0; fi
      return 1
      ;;
  esac
  return 1
}}
check_docker
status=$?
printf 'RESULT=%s INFO_CALLS=%s START_CALLS=%s SLEEP_CALLS=%s DOCKER_COMPOSE=%s\\n' \\
  "$status" "$info_calls" "$start_calls" "$sleep_calls" "${{DOCKER_COMPOSE:-}}"
exit "$status"
"""


def _run_bash(script: str) -> subprocess.CompletedProcess[str]:
    assert BASH is not None
    return subprocess.run(
        [BASH, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )


def _run_bash_with_tty(
    script: str,
    input_text: str,
    *,
    before_input=None,
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
    prompt = b"or type Q to quit:"

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

        if before_input is not None:
            before_input()
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
def test_macos_docker_preflight_accepts_ready_daemon_without_starting_desktop() -> None:
    result = _run_bash(_bash_harness())

    assert result.returncode == 0
    assert "RESULT=0" in result.stdout
    assert "START_CALLS=0" in result.stdout
    assert "DOCKER_COMPOSE=docker compose" in result.stdout


@pytest.mark.skipif(BASH is None or os.name == "nt", reason="Requires POSIX Bash")
def test_macos_docker_preflight_starts_desktop_and_waits_for_daemon() -> None:
    result = _run_bash(_bash_harness(ready_after=2))

    assert result.returncode == 0
    assert "START_CALLS=1" in result.stdout
    assert "RESULT=0" in result.stdout


@pytest.mark.skipif(BASH is None or os.name == "nt", reason="Requires POSIX Bash")
def test_linux_docker_preflight_does_not_start_engine_automatically() -> None:
    result = _run_bash(_bash_harness(platform="Linux", ready_after=1000))

    assert result.returncode == 1
    assert "Docker Engine is not available." in result.stderr
    assert "sudo systemctl start docker" in result.stderr
    assert "START_CALLS=0" in result.stdout
    assert "SLEEP_CALLS=0" in result.stdout
    assert "Press Enter to retry Docker checks" not in result.stderr


@pytest.mark.skipif(BASH is None or os.name == "nt", reason="Requires POSIX TTY")
def test_linux_enter_rechecks_engine_after_user_starts_it() -> None:
    result = _run_bash_with_tty(
        _bash_harness(platform="Linux", ready_after=4),
        "\n",
    )

    assert result.returncode == 0
    assert "Docker Engine is not available." in result.stdout
    assert "RESULT=0" in result.stdout
    assert "START_CALLS=0" in result.stdout


@pytest.mark.skipif(BASH is None or os.name == "nt", reason="Requires POSIX Bash")
def test_headless_macos_failure_has_instructions_and_does_not_prompt() -> None:
    result = _run_bash(_bash_harness(ready_after=1000))

    assert result.returncode == 1
    assert "Docker Engine is not reachable." in result.stderr
    assert "Run SPX Setup again" in result.stderr
    assert "Press Enter to retry Docker checks" not in result.stderr


@pytest.mark.skipif(BASH is None or os.name == "nt", reason="Requires POSIX Bash")
def test_missing_cli_can_be_installed_and_found_after_enter(tmp_path: Path) -> None:
    cli_marker = tmp_path / "docker-installed"
    script = _bash_harness(
        cli_present=False,
        ready_after=1,
        cli_marker=str(cli_marker),
    )
    result = _run_bash_with_tty(
        script,
        "\n",
        before_input=lambda: cli_marker.touch(),
    )

    assert result.returncode == 0
    assert (
        "Install Docker Desktop from https://www.docker.com/products/docker-desktop/"
        in result.stdout + result.stderr
    )
    assert "RESULT=0" in result.stdout


@pytest.mark.skipif(BASH is None or os.name == "nt", reason="Requires POSIX TTY")
def test_enter_retries_daemon_check_and_q_quits() -> None:
    # Enter rechecks the daemon after the automatic startup wait without
    # launching Docker Desktop a second time.
    retry = _run_bash_with_tty(_bash_harness(ready_after=34), "\n")
    assert retry.returncode == 0
    assert "Attempting to start Docker Desktop" in retry.stdout
    assert "START_CALLS=1" in retry.stdout
    assert "RESULT=0" in retry.stdout

    quit_result = _run_bash_with_tty(_bash_harness(ready_after=1000), "Q\n")
    assert quit_result.returncode == 1
    assert "Docker preflight cancelled by the user" in quit_result.stdout


@pytest.mark.skipif(BASH is None or os.name == "nt", reason="Requires POSIX TTY")
def test_missing_compose_has_separate_instructions_and_enter_rechecks(
    tmp_path: Path,
) -> None:
    compose_marker = tmp_path / "compose-installed"
    script = _bash_harness(compose_present=False, compose_marker=str(compose_marker))
    result = _run_bash_with_tty(
        script,
        "\n",
        before_input=lambda: compose_marker.touch(),
    )

    assert result.returncode == 0
    assert "Docker Compose is not available." in result.stdout
    assert "Docker Desktop includes the Docker Compose plugin." in result.stdout
    assert (
        "Press Enter to check Docker CLI, Engine, and Compose again, or type Q to quit:"
        in result.stdout
    )
    assert "wait up to 60 seconds" not in result.stdout
    assert "RESULT=0" in result.stdout
    assert "START_CALLS=0" in result.stdout
    assert "SLEEP_CALLS=0" in result.stdout


@pytest.mark.skipif(BASH is None or os.name == "nt", reason="Requires POSIX Bash")
def test_macos_desktop_app_fallback_does_not_require_docker_cli() -> None:
    helper = str(SHELL_HELPER).replace("'", "'\\''")
    script = f"""
source '{helper}'
spx_resolve_docker_cli() {{ return 1; }}
open() {{ [[ "$1" == "-a" && "$2" == "Docker" ]]; }}
spx_start_docker_desktop macOS
"""
    result = _run_bash(script)

    assert result.returncode == 0
    assert "Opened Docker Desktop" in result.stdout


@pytest.mark.skipif(BASH is None or os.name == "nt", reason="Requires POSIX Bash")
def test_macos_recovery_messages_distinguish_cli_engine_permissions_and_compose() -> (
    None
):
    helper = str(SHELL_HELPER).replace("'", "'\\''")
    script = f"""
source '{helper}'
spx_print_recovery_instructions cli macOS ''
spx_print_recovery_instructions daemon macOS 'permission denied'
spx_print_recovery_instructions compose macOS ''
"""
    result = _run_bash(script)

    assert result.returncode == 0
    assert "Docker CLI was not found." in result.stdout
    assert (
        "Then open Docker Desktop and wait until Docker Engine is running."
        in result.stdout
    )
    assert "this account cannot access Docker Engine" in result.stdout
    assert "ask your administrator to check permissions" in result.stdout
    assert "Docker Compose is not available." in result.stdout


@pytest.mark.skipif(BASH is None or os.name == "nt", reason="Requires POSIX Bash")
def test_preflight_classifier_only_selects_stack_starting_commands() -> None:
    helper = str(SHELL_HELPER).replace("'", "'\\''")
    script = f"""
source '{helper}'
spx_docker_preflight_required --help && exit 1
spx_docker_preflight_required generate --protocols bacnet --no-start && exit 1
spx_docker_preflight_required bootstrap --bundle bundle.json && exit 1
spx_docker_preflight_required generate --protocols bacnet && exit 1
spx_docker_preflight_required generate --protocols bacnet --start || exit 1
spx_docker_preflight_required generate || exit 1
exit 0
"""
    result = _run_bash(script)
    assert result.returncode == 0


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


def _run_windows_powershell(body: str) -> subprocess.CompletedProcess[str]:
    assert WINDOWS_POWERSHELL is not None
    return subprocess.run(
        [
            WINDOWS_POWERSHELL,
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
$script:probeCalls = 0
$script:readyAfter = READY_AFTER_PLACEHOLDER
$script:cliPresent = CLI_PRESENT_PLACEHOLDER
$script:composePresent = COMPOSE_PRESENT_PLACEHOLDER
$script:startCalls = 0
$script:promptAvailable = $true
$script:promptAction = ''
$script:lastPrompt = ''
$script:fakeElapsedMilliseconds = 0
$script:platform = 'PLATFORM_PLACEHOLDER'
function Get-DockerDesktopPlatform { return $script:platform }
function Resolve-DockerCli {
  if (-not $script:cliPresent) { $script:DockerCliPath = $null; return $false }
  $script:DockerCliPath = 'mock-docker'
  return $true
}
function Invoke-DockerInfo {
  param([int]$TimeoutMilliseconds = 5000)
  $script:infoCalls++
  if ($script:infoCalls -ge $script:readyAfter) {
    return [PSCustomObject]@{ ExitCode = 0; StdOut = ''; StdErr = '' }
  }
  return [PSCustomObject]@{ ExitCode = 1; StdOut = ''; StdErr = 'cannot connect to docker API' }
}
function Invoke-DockerEngineVersionProbe {
  param([int]$TimeoutMilliseconds = 5000)
  $script:probeCalls++
  if ($script:probeCalls -ge $script:readyAfter) {
    return [PSCustomObject]@{ ExitCode = 0; StdOut = '29.8.0'; StdErr = '' }
  }
  return [PSCustomObject]@{ ExitCode = 1; StdOut = ''; StdErr = 'cannot connect to docker API' }
}
function Resolve-DockerCompose {
  if ($script:composePresent) { return 'docker compose' }
  return $null
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
function Test-DockerPromptAvailable { return $script:promptAvailable }
function Read-Host {
  param([string]$Prompt)
  $script:lastPrompt = $Prompt
  if ($script:promptAction -eq 'quit') { return 'Q' }
  if ($script:promptAction -eq 'install-cli') {
    $script:cliPresent = $true
    $script:readyAfter = $script:probeCalls + 1
    return ''
  }
  if ($script:promptAction -eq 'start-daemon') {
    $script:readyAfter = $script:probeCalls + 1
    return ''
  }
  if ($script:promptAction -eq 'start-daemon-delayed') {
    $script:readyAfter = $script:probeCalls + 3
    return ''
  }
  if ($script:promptAction -eq 'install-compose') {
    $script:composePresent = $true
    return ''
  }
  return ''
}
"""


def _ps_mocks(
    *,
    platform: str = "Windows",
    cli_present: bool = True,
    ready_after: int = 1,
    compose_present: bool = True,
) -> str:
    return (
        _POWERSHELL_MOCKS.replace("READY_AFTER_PLACEHOLDER", str(ready_after))
        .replace("CLI_PRESENT_PLACEHOLDER", "$true" if cli_present else "$false")
        .replace(
            "COMPOSE_PRESENT_PLACEHOLDER", "$true" if compose_present else "$false"
        )
        .replace("PLATFORM_PLACEHOLDER", platform)
    )


@pytest.mark.skipif(
    WINDOWS_POWERSHELL is None, reason="Requires Windows PowerShell 5.1"
)
def test_windows_powershell_51_captures_native_output_and_exit_code() -> None:
    body = r"""
$success = Invoke-NativeCapture -Command $env:ComSpec -ArgumentList @('/d', '/c', 'echo SPX_NATIVE_CAPTURE_OK') -TimeoutMilliseconds 5000
if ($success.ExitCode -ne 0 -or $success.StdOut -notmatch 'SPX_NATIVE_CAPTURE_OK') { throw "wrong successful process result: $($success | ConvertTo-Json -Compress)" }
$failure = Invoke-NativeCapture -Command $env:ComSpec -ArgumentList @('/d', '/c', 'exit 7') -TimeoutMilliseconds 5000
if ($failure.ExitCode -ne 7) { throw "wrong failed process exit code: $($failure.ExitCode)" }
'PREFLIGHT_TEST_PASSED'
"""
    result = _run_windows_powershell(body)
    assert result.returncode == 0, result.stderr
    assert "PREFLIGHT_TEST_PASSED" in result.stdout


@pytest.mark.skipif(
    WINDOWS_POWERSHELL is None, reason="Requires Windows PowerShell 5.1"
)
def test_windows_powershell_51_native_capture_keeps_output_when_timed_out() -> None:
    body = r"""
$childShell = Join-Path $PSHOME 'powershell.exe'
$childCommand = 'Write-Output SPX_PARTIAL_OUTPUT; Start-Sleep -Seconds 30'
$result = Invoke-NativeCapture -Command $childShell -ArgumentList @('-NoProfile', '-Command', $childCommand) -TimeoutMilliseconds 1500
if ($result.ExitCode -ne 124) { throw "wrong timeout exit code: $($result.ExitCode)" }
if ($result.StdOut -notmatch 'SPX_PARTIAL_OUTPUT') { throw 'partial standard output was lost after timeout' }
if ($result.StdErr -notmatch 'timed out after 1500 ms') { throw 'timeout detail was not reported' }
'PREFLIGHT_TEST_PASSED'
"""
    result = _run_windows_powershell(body)
    assert result.returncode == 0, result.stderr
    assert "PREFLIGHT_TEST_PASSED" in result.stdout


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is not available")
def test_windows_preflight_accepts_ready_daemon_without_starting_desktop() -> None:
    body = (
        _ps_mocks()
        + r"""
$result = Check-Docker
if ($result -ne 'docker compose' -or $script:startCalls -ne 0) { throw 'unexpected result' }
'PREFLIGHT_TEST_PASSED'
"""
    )
    result = _run_powershell(body)
    assert result.returncode == 0, result.stderr
    assert "PREFLIGHT_TEST_PASSED" in result.stdout


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is not available")
def test_windows_engine_ready_when_info_exit_is_nonzero_but_server_version_succeeds() -> (
    None
):
    body = (
        _ps_mocks(ready_after=999)
        + r"""
function Invoke-DockerInfo {
  param([int]$TimeoutMilliseconds = 5000)
  return [PSCustomObject]@{
    ExitCode = 1
    StdOut = "Server Version: 29.8.0`nContainers: 7`n Running: 4`n Stopped: 3"
    StdErr = 'errors pretty printing info'
  }
}
function Invoke-DockerEngineVersionProbe {
  param([int]$TimeoutMilliseconds = 5000)
  return [PSCustomObject]@{ ExitCode = 0; StdOut = '29.8.0'; StdErr = '' }
}
$state = Test-DockerState
if (-not $state.Ready -or $state.Failure -or $state.Compose -ne 'docker compose') { throw 'server version probe did not establish Engine readiness' }
if ($script:startCalls -ne 0) { throw 'Docker Desktop was unnecessarily restarted' }
'PREFLIGHT_TEST_PASSED'
"""
    )
    result = _run_powershell(body)
    assert result.returncode == 0, result.stderr
    assert "PREFLIGHT_TEST_PASSED" in result.stdout


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is not available")
def test_windows_partial_info_output_does_not_replace_failed_server_probe() -> None:
    body = (
        _ps_mocks(ready_after=999)
        + r"""
function Invoke-DockerInfo {
  param([int]$TimeoutMilliseconds = 5000)
  return [PSCustomObject]@{
    ExitCode = 1
    StdOut = "Server Version: 29.8.0`nContainers: 7`n Running: 4`n Stopped: 3"
    StdErr = 'docker info returned a nonzero exit code'
  }
}
function Invoke-DockerEngineVersionProbe {
  param([int]$TimeoutMilliseconds = 5000)
  return [PSCustomObject]@{ ExitCode = 1; StdOut = '29.8.0'; StdErr = 'server check timed out' }
}
$state = Test-DockerState
if ($state.Ready -or $state.Failure -ne 'daemon') { throw 'partial info output incorrectly passed readiness' }
$detail = Get-DockerInfoDetail -Result $state.Result
if ($detail -notmatch 'Server Version: 29.8.0' -or $detail -notmatch 'server check timed out') { throw 'diagnostic output was not preserved' }
'PREFLIGHT_TEST_PASSED'
"""
    )
    result = _run_powershell(body)
    assert result.returncode == 0, result.stderr
    assert "PREFLIGHT_TEST_PASSED" in result.stdout


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is not available")
def test_windows_preflight_starts_desktop_and_waits_for_daemon() -> None:
    body = (
        _ps_mocks(ready_after=2)
        + r"""
$result = Check-Docker
if ($result -ne 'docker compose' -or $script:startCalls -ne 1) { throw 'unexpected result' }
'PREFLIGHT_TEST_PASSED'
"""
    )
    result = _run_powershell(body)
    assert result.returncode == 0, result.stderr
    assert "PREFLIGHT_TEST_PASSED" in result.stdout


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is not available")
def test_windows_enter_retries_after_user_starts_daemon() -> None:
    body = (
        _ps_mocks(ready_after=33).replace(
            "$script:promptAction = ''", "$script:promptAction = 'start-daemon-delayed'"
        )
        + r"""
$result = Check-Docker
if ($result -ne 'docker compose' -or $script:startCalls -ne 1) { throw 'Docker Desktop was started again during manual retry' }
if ($script:lastPrompt -ne 'Press Enter to retry Docker checks (wait up to 60 seconds), or type Q to quit:') { throw 'wrong retry prompt' }
if ($script:fakeElapsedMilliseconds -le 0) { throw 'daemon wait did not run after Enter' }
'PREFLIGHT_TEST_PASSED'
"""
    )
    result = _run_powershell(body)
    assert result.returncode == 0, result.stderr
    assert "PREFLIGHT_TEST_PASSED" in result.stdout


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is not available")
def test_missing_cli_is_rechecked_after_enter_without_runner_docker_dependency() -> (
    None
):
    body = (
        _ps_mocks(cli_present=False).replace(
            "$script:promptAction = ''", "$script:promptAction = 'install-cli'"
        )
        + r"""
$result = Check-Docker
if ($result -ne 'docker compose') { throw 'unexpected result' }
'PREFLIGHT_TEST_PASSED'
"""
    )
    result = _run_powershell(body)
    assert result.returncode == 0, result.stderr
    assert "Docker CLI was not found." in result.stderr
    assert "PREFLIGHT_TEST_PASSED" in result.stdout


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is not available")
def test_missing_compose_uses_separate_instructions_and_rechecks_after_enter() -> None:
    body = (
        _ps_mocks(compose_present=False).replace(
            "$script:promptAction = ''", "$script:promptAction = 'install-compose'"
        )
        + r"""
$result = Check-Docker
if ($result -ne 'docker compose' -or $script:startCalls -ne 0) { throw 'unexpected result' }
if ($script:lastPrompt -ne 'Press Enter to check Docker CLI, Engine, and Compose again, or type Q to quit:') { throw 'wrong retry prompt for missing Compose' }
if ($script:fakeElapsedMilliseconds -ne 0) { throw 'Compose retry should recheck immediately' }
'PREFLIGHT_TEST_PASSED'
"""
    )
    result = _run_powershell(body)
    assert result.returncode == 0, result.stderr
    assert "Docker Compose is not available." in result.stderr
    assert "Docker Desktop includes the Docker Compose plugin." in result.stderr
    assert "PREFLIGHT_TEST_PASSED" in result.stdout


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is not available")
def test_q_quits_when_compose_is_missing_without_waiting_or_starting_desktop() -> None:
    body = (
        _ps_mocks(compose_present=False).replace(
            "$script:promptAction = ''", "$script:promptAction = 'quit'"
        )
        + r"""
try { Check-Docker | Out-Null; throw 'expected failure' } catch {
  if ($_.Exception.Message -notmatch 'cancelled by the user') { throw }
  if ($script:startCalls -ne 0 -or $script:fakeElapsedMilliseconds -ne 0) { throw 'Compose quit triggered recovery work' }
  if ($script:lastPrompt -ne 'Press Enter to check Docker CLI, Engine, and Compose again, or type Q to quit:') { throw 'wrong Compose quit prompt' }
  'PREFLIGHT_TEST_PASSED'
}
"""
    )
    result = _run_powershell(body)
    assert result.returncode == 0, result.stderr
    assert "PREFLIGHT_TEST_PASSED" in result.stdout


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is not available")
def test_q_quits_and_headless_mode_returns_actionable_instructions() -> None:
    quit_body = (
        _ps_mocks(ready_after=999).replace(
            "$script:promptAction = ''", "$script:promptAction = 'quit'"
        )
        + r"""
try { Check-Docker | Out-Null; throw 'expected failure' } catch {
  if ($_.Exception.Message -notmatch 'cancelled by the user') { throw }
  'PREFLIGHT_TEST_PASSED'
}
"""
    )
    quit_result = _run_powershell(quit_body)
    assert quit_result.returncode == 0, quit_result.stderr
    assert "PREFLIGHT_TEST_PASSED" in quit_result.stdout

    headless_body = (
        _ps_mocks(ready_after=999).replace(
            "$script:promptAvailable = $true", "$script:promptAvailable = $false"
        )
        + r"""
try { Check-Docker | Out-Null; throw 'expected failure' } catch {
  if ($_.Exception.Message -notmatch 'Run SPX Setup again') { throw }
  'PREFLIGHT_TEST_PASSED'
}
"""
    )
    headless_result = _run_powershell(headless_body)
    assert headless_result.returncode == 0, headless_result.stderr
    assert "PREFLIGHT_TEST_PASSED" in headless_result.stdout


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is not available")
def test_windows_recovery_messages_give_specific_next_steps() -> None:
    body = r"""
$permission = [PSCustomObject]@{ ExitCode = 1; StdOut = ''; StdErr = 'permission denied while connecting to the Docker daemon' }
$unavailable = [PSCustomObject]@{ ExitCode = 1; StdOut = ''; StdErr = 'cannot connect to docker API' }
Write-DockerRecoveryInstructions -Failure 'cli' -Platform 'Windows' -Result $null
Write-DockerRecoveryInstructions -Failure 'daemon' -Platform 'Windows' -Result $unavailable
Write-DockerRecoveryInstructions -Failure 'daemon' -Platform 'Windows' -Result $permission
Write-DockerRecoveryInstructions -Failure 'compose' -Platform 'Windows' -Result $null
"""
    result = _run_powershell(body)

    assert result.returncode == 0, result.stderr
    assert "Docker CLI was not found." in result.stderr
    assert "Docker Engine is not reachable." in result.stderr
    assert "this account cannot access Docker Engine" in result.stderr
    assert "ask your administrator to check permissions" in result.stderr
    assert "Docker Compose is not available." in result.stderr


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is not available")
def test_linux_preflight_gives_engine_steps_without_desktop_autostart() -> None:
    body = (
        _ps_mocks(platform="Linux", ready_after=999).replace(
            "$script:promptAvailable = $true", "$script:promptAvailable = $false"
        )
        + r"""
try { Check-Docker | Out-Null; throw 'expected failure' } catch {
  if ($_.Exception.Message -notmatch 'Run SPX Setup again') { throw }
  if ($script:startCalls -ne 0) { throw 'Linux must not start Desktop' }
  'PREFLIGHT_TEST_PASSED'
}
"""
    )
    result = _run_powershell(body)
    assert result.returncode == 0, result.stderr
    assert "Docker Engine is not available." in result.stderr
    assert "sudo systemctl start docker" in result.stderr
    assert "PREFLIGHT_TEST_PASSED" in result.stdout


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is not available")
def test_linux_enter_rechecks_engine_after_user_starts_it() -> None:
    body = (
        _ps_mocks(platform="Linux", ready_after=999).replace(
            "$script:promptAction = ''", "$script:promptAction = 'start-daemon-delayed'"
        )
        + r"""
$result = Check-Docker
if ($result -ne 'docker compose' -or $script:startCalls -ne 0) { throw 'unexpected result' }
if ($script:lastPrompt -ne 'Press Enter to retry Docker checks (wait up to 60 seconds), or type Q to quit:') { throw 'wrong retry prompt' }
if ($script:fakeElapsedMilliseconds -le 0) { throw 'daemon wait did not run after Enter' }
'PREFLIGHT_TEST_PASSED'
"""
    )
    result = _run_powershell(body)
    assert result.returncode == 0, result.stderr
    assert "Docker Engine is not available." in result.stderr
    assert "PREFLIGHT_TEST_PASSED" in result.stdout


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is not available")
def test_windows_desktop_cli_launch_uses_bounded_startup_process() -> None:
    body = r"""
$ErrorActionPreference = 'Stop'
$script:DockerCliPath = 'mock-docker.exe'
$script:capturedArguments = ''
$script:fakeProcess = $null
function Get-DockerDesktopPlatform { return 'Windows' }
function Resolve-DockerCli { $script:DockerCliPath = 'mock-docker.exe'; return $true }
function Start-Process {
  param([string]$FilePath, [string[]]$ArgumentList = @(), [switch]$NoNewWindow, [switch]$PassThru, [System.Management.Automation.ActionPreference]$ErrorAction)
  $script:capturedArguments = $ArgumentList -join ' '
  $process = [PSCustomObject]@{ ExitCode = 0; WaitTimeoutMs = 0 }
  $process | Add-Member -MemberType ScriptMethod -Name WaitForExit -Value {
    param([int]$TimeoutMs)
    $this.WaitTimeoutMs = $TimeoutMs
    return $false
  }
  $script:fakeProcess = $process
  return $process
}
if (-not (Start-DockerDesktop)) { throw 'desktop was not started' }
if ($script:capturedArguments -ne 'desktop start --detach') { throw 'unexpected startup args' }
if ($script:fakeProcess.WaitTimeoutMs -ne 2000) { throw 'startup process was not bounded' }
'PREFLIGHT_TEST_PASSED'
"""
    result = _run_powershell(body)
    assert result.returncode == 0, result.stderr
    assert "PREFLIGHT_TEST_PASSED" in result.stdout


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is not available")
def test_windows_desktop_start_request_handles_missing_process_exit_code() -> None:
    body = r"""
$ErrorActionPreference = 'Stop'
$script:DockerCliPath = 'mock-docker.exe'
function Get-DockerDesktopPlatform { return 'Windows' }
function Resolve-DockerCli { $script:DockerCliPath = 'mock-docker.exe'; return $true }
function Start-Process {
  param([string]$FilePath, [string[]]$ArgumentList = @(), [switch]$NoNewWindow, [switch]$PassThru, [System.Management.Automation.ActionPreference]$ErrorAction)
  $process = [PSCustomObject]@{ ExitCode = $null; WaitTimeoutMs = 0 }
  $process | Add-Member -MemberType ScriptMethod -Name WaitForExit -Value {
    param([int]$TimeoutMs)
    $this.WaitTimeoutMs = $TimeoutMs
    return $true
  }
  return $process
}
if (-not (Start-DockerDesktop)) { throw 'a completed startup request with an unavailable exit code was treated as a failed launch' }
'PREFLIGHT_TEST_PASSED'
"""
    result = _run_powershell(body)
    assert result.returncode == 0, result.stderr
    assert "PREFLIGHT_TEST_PASSED" in result.stdout


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is not available")
def test_docker_cli_resolution_rechecks_common_install_locations() -> None:
    body = r"""
$ErrorActionPreference = 'Stop'
$script:expectedDockerPath = '/usr/local/bin/docker'
function Get-Command { param([string]$Name, $ErrorAction); return $null }
function Test-Path { param([string]$LiteralPath, [string]$PathType); return ($LiteralPath -eq $script:expectedDockerPath) }
if (-not (Resolve-DockerCli)) { throw 'fallback Docker CLI was not found' }
if ($script:DockerCliPath -ne $script:expectedDockerPath) { throw 'wrong Docker CLI fallback path' }
'PREFLIGHT_TEST_PASSED'
"""
    result = _run_powershell(body)
    assert result.returncode == 0, result.stderr
    assert "PREFLIGHT_TEST_PASSED" in result.stdout


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is not available")
def test_powershell_preflight_classifier_skips_artifact_only_commands() -> None:
    body = r"""
if (Test-DockerPreflightRequired @('--help')) { throw 'help should not need Docker' }
if (Test-DockerPreflightRequired @('generate','--protocols','bacnet','--no-start')) { throw 'no-start should not need Docker' }
if (Test-DockerPreflightRequired @('generate','--protocols','bacnet')) { throw 'noninteractive generation should not need Docker' }
if (Test-DockerPreflightRequired @('bootstrap','--bundle','bundle.json')) { throw 'bootstrap should not need Docker' }
if (-not (Test-DockerPreflightRequired @())) { throw 'interactive setup should need Docker' }
if (-not (Test-DockerPreflightRequired @('generate','--protocols','bacnet','--start'))) { throw '--start should need Docker' }
'PREFLIGHT_TEST_PASSED'
"""
    result = _run_powershell(body)
    assert result.returncode == 0, result.stderr
    assert "PREFLIGHT_TEST_PASSED" in result.stdout


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is not available")
def test_wait_for_daemon_bounds_each_probe_and_total_wait() -> None:
    body = r"""
$ErrorActionPreference = 'Stop'
$script:fakeElapsedMilliseconds = 0
$script:probeTimeouts = @()
function Resolve-DockerCli { $script:DockerCliPath = 'mock-docker'; return $true }
function New-DockerPreflightTimer { return [PSCustomObject]@{} }
function Get-DockerPreflightElapsedMilliseconds { param($Timer); return $script:fakeElapsedMilliseconds }
function Invoke-DockerPreflightSleep { param([int]$Milliseconds = 2000); $script:fakeElapsedMilliseconds += $Milliseconds }
function Invoke-DockerEngineVersionProbe {
  param([int]$TimeoutMilliseconds = 5000)
  $script:probeTimeouts += $TimeoutMilliseconds
  $script:fakeElapsedMilliseconds += $TimeoutMilliseconds
  return [PSCustomObject]@{ ExitCode = 124; StdOut = '29.8.0'; StdErr = 'server version probe timed out' }
}
$result = Wait-DockerDaemon -TimeoutSeconds 5
if ($result.Connected) { throw 'unexpected connection' }
if ($script:fakeElapsedMilliseconds -ne 5000) { throw 'wait exceeded its deadline' }
if ($script:probeTimeouts.Count -ne 3 -or $script:probeTimeouts[-1] -ne 1000) { throw 'probe timeouts were not bounded' }
'PREFLIGHT_TEST_PASSED'
"""
    result = _run_powershell(body)
    assert result.returncode == 0, result.stderr
    assert "PREFLIGHT_TEST_PASSED" in result.stdout
