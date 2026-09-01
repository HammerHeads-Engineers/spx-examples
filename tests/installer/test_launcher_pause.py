# SPDX-License-Identifier: MIT

from __future__ import annotations

import errno
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import time

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
BASH = "/bin/bash"
pytestmark = pytest.mark.skipif(os.name == "nt", reason="The shell launcher tests are POSIX-only.")


def _setup_wrapper_command(
    tmp_path: Path, *args: str, exit_code: int = 0
) -> list[str]:
    wrapper = tmp_path / "spx-setup.sh"
    wrapper.write_text((REPO_ROOT / "spx-setup.sh").read_text(encoding="utf-8"), encoding="utf-8")
    installer = tmp_path / "spx-install.sh"
    installer.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' child-output\n"
        f"exit {exit_code}\n",
        encoding="utf-8",
    )
    installer.chmod(0o755)

    return [BASH, str(wrapper), *args]


def _run_setup_wrapper(
    tmp_path: Path, *args: str, exit_code: int = 0
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        _setup_wrapper_command(tmp_path, *args, exit_code=exit_code),
        cwd=tmp_path,
        input="",
        capture_output=True,
        text=True,
        check=False,
    )


def test_setup_wrapper_preserves_success_without_pause_flag(tmp_path: Path) -> None:
    result = _run_setup_wrapper(tmp_path)

    assert result.returncode == 0
    assert "child-output" in result.stdout
    assert "Press ENTER to close..." not in result.stdout


def test_setup_wrapper_does_not_block_or_change_success_without_tty(tmp_path: Path) -> None:
    result = _run_setup_wrapper(tmp_path, "--pause-on-exit")

    assert result.returncode == 0
    assert "child-output" in result.stdout
    assert "Press ENTER to close..." not in result.stdout


def test_setup_wrapper_preserves_error_code_without_tty(tmp_path: Path) -> None:
    result = _run_setup_wrapper(tmp_path, "--pause-on-exit", exit_code=7)

    assert result.returncode == 7
    assert "child-output" in result.stdout
    assert "Press ENTER to close..." not in result.stdout


def _run_with_pty(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    master_fd, slave_fd = os.openpty()
    process = subprocess.Popen(
        command,
        cwd=cwd,
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        close_fds=True,
        start_new_session=True,
    )
    os.close(slave_fd)
    output = bytearray()
    deadline = time.monotonic() + 5

    def kill_process_tree() -> None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (PermissionError, ProcessLookupError):
            process.kill()

    try:
        while time.monotonic() < deadline and b"Press ENTER to close..." not in output:
            ready, _, _ = select.select([master_fd], [], [], 0.1)
            if not ready:
                continue
            try:
                output.extend(os.read(master_fd, 4096))
            except OSError as exc:
                if exc.errno == errno.EIO:
                    break
                raise

        if b"Press ENTER to close..." not in output:
            kill_process_tree()
            process.wait(timeout=5)
            pytest.fail("The launcher did not reach its interactive pause prompt.")

        assert process.poll() is None
        os.write(master_fd, b"\n")
        post_input_deadline = time.monotonic() + 5
        while process.poll() is None and time.monotonic() < post_input_deadline:
            ready, _, _ = select.select([master_fd], [], [], 0.1)
            if not ready:
                continue
            try:
                output.extend(os.read(master_fd, 4096))
            except OSError as exc:
                if exc.errno == errno.EIO:
                    break
                raise
        if process.poll() is None:
            kill_process_tree()
        returncode = process.wait(timeout=5)
    finally:
        os.close(master_fd)

    return subprocess.CompletedProcess(
        command,
        returncode,
        stdout=output.decode(errors="replace"),
        stderr="",
    )


def test_setup_wrapper_pauses_after_success_on_tty(tmp_path: Path) -> None:
    result = _run_with_pty(
        _setup_wrapper_command(tmp_path, "--pause-on-exit"),
        tmp_path,
    )

    assert result.returncode == 0
    assert "child-output" in result.stdout
    assert "Press ENTER to close..." in result.stdout


def test_setup_wrapper_pauses_after_error_and_preserves_code_on_tty(tmp_path: Path) -> None:
    result = _run_with_pty(
        _setup_wrapper_command(tmp_path, "--pause-on-exit", exit_code=7),
        tmp_path,
    )

    assert result.returncode == 7
    assert "child-output" in result.stdout
    assert "Press ENTER to close..." in result.stdout


def test_mcp_setup_help_accepts_pause_flag_without_tty() -> None:
    result = subprocess.run(
        [BASH, str(REPO_ROOT / "spx-mcp-setup.sh"), "--help", "--pause-on-exit"],
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHON_BIN": sys.executable},
        input="",
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "--pause-on-exit" in result.stdout
    assert "Unsupported argument: --pause-on-exit" not in result.stderr


def test_mcp_setup_pauses_after_success_and_error_on_tty() -> None:
    command = [BASH, str(REPO_ROOT / "spx-mcp-setup.sh"), "--help", "--pause-on-exit"]
    result = _run_with_pty(command, REPO_ROOT)

    assert result.returncode == 0
    assert "--pause-on-exit" in result.stdout
    assert "Press ENTER to close..." in result.stdout

    error_result = _run_with_pty(
        [BASH, str(REPO_ROOT / "spx-mcp-setup.sh"), "--unsupported", "--pause-on-exit"],
        REPO_ROOT,
    )

    assert error_result.returncode == 1
    assert "Unsupported argument: --unsupported" in error_result.stdout
    assert "Press ENTER to close..." in error_result.stdout


def test_linux_desktop_launcher_requests_optional_pause() -> None:
    desktop = (REPO_ROOT / "spx-setup.desktop").read_text(encoding="utf-8")

    assert "Terminal=true" in desktop
    assert "bash ./spx-setup.sh --pause-on-exit" in desktop
