"""Regression coverage for concurrent Setup monitor, MCP and worker processes."""

from contextlib import contextmanager
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest

from installer import setup_session as module
from installer.setup_session import SetupEngine, SetupError, atomic_json

KEY = "AAAAA-AAAAA-AAAAA-AAAAA-AAAAA-AAAAA"


@pytest.fixture
def draft(tmp_path):
    engine = SetupEngine(tmp_path / "private")
    session = engine.create(tmp_path / "active", KEY, initial={"start": False})
    return engine, session


def test_status_does_not_wait_for_planning_process_lock(draft):
    engine, session = draft
    script = (
        "from installer.setup_session import file_lock; "
        "from pathlib import Path; import sys,time\n"
        "with file_lock(Path(sys.argv[1])):\n"
        " print('locked',flush=True); time.sleep(7)\n"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(engine.root / "sessions.lock")],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout.readline().strip() == "locked"
        started = time.monotonic()
        assert engine.get(session["session_id"])["status"] == "DRAFT"
        assert time.monotonic() - started < 1
    finally:
        process.terminate()
        process.wait(timeout=10)
        process.stdout.close()


def test_worker_recovery_rereads_final_result_under_lock(draft, monkeypatch):
    engine, session = draft
    session = engine._read(session["session_id"])
    session.update(status="APPLYING", job={"job_id": "job", "pid": 123})
    engine._write(session)
    monkeypatch.setattr(module, "_pid_alive", lambda _: False)

    @contextmanager
    def completing_worker(_):
        current = engine._read(session["session_id"])
        current.update(status="SUCCEEDED", stage="complete")
        engine._write(current)
        yield

    monkeypatch.setattr(module, "file_lock", completing_worker)
    assert engine.get(session["session_id"])["status"] == "SUCCEEDED"


def test_monitor_retries_busy_instead_of_exiting(draft, monkeypatch, capsys):
    from installer import setup_workspace, terminal_selection

    engine, session = draft
    calls = iter(
        [SetupError("busy", "SETUP_BUSY"), {"status": "SUCCEEDED", "stage": "complete"}]
    )

    def get(_):
        value = next(calls)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(engine, "get", get)
    monkeypatch.setattr(terminal_selection, "is_interactive", lambda: True)
    monkeypatch.setattr(time, "sleep", lambda _: None)
    assert setup_workspace.monitor(engine, session["session_id"]) == 0
    assert "busy" not in capsys.readouterr().out.lower()


@pytest.mark.skipif(os.name != "nt", reason="Native Windows file sharing")
def test_atomic_json_retries_while_windows_reader_holds_file(tmp_path):
    path = tmp_path / "state.json"
    atomic_json(path, {"revision": 1})
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.restype = ctypes.c_void_p
    kernel.CreateFileW.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_void_p,
    ]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.CreateFileW(str(path), 0x80000000, 1 | 2, None, 3, 0, None)
    assert handle != ctypes.c_void_p(-1).value
    released = threading.Event()

    def release():
        time.sleep(0.2)
        kernel.CloseHandle(handle)
        released.set()

    thread = threading.Thread(target=release)
    thread.start()
    try:
        atomic_json(path, {"revision": 2})
    finally:
        thread.join(timeout=3)
    assert released.is_set()
    assert json.loads(path.read_text())["revision"] == 2
    assert not list(tmp_path.glob("*.tmp"))


def test_progress_io_error_does_not_abandon_running_stack(draft, monkeypatch):
    engine, session = draft
    private = engine._read(session["session_id"])
    private["plan"] = {
        "preflight": {"existing": [], "port_options": []},
        "_stage": str(Path(private["output"])),
    }
    private["job"] = {"job_id": "job"}
    monkeypatch.setattr(
        module, "_endpoints", lambda _: {"api": "http://127.0.0.1:8000"}
    )
    waited = []

    class Stream:
        def __iter__(self):
            return iter(["Container creating\n", "Stack ready\n"])

        def close(self):
            pass

    class Process:
        stdout = Stream()

        def wait(self, timeout=None):
            waited.append(True)
            return 0

    monkeypatch.setattr(module.subprocess, "Popen", lambda *a, **k: Process())
    real_write = atomic_json

    def write(path, value):
        if path.name == "progress.json":
            raise PermissionError("reader is holding the progress file")
        real_write(path, value)

    monkeypatch.setattr(module, "atomic_json", write)
    engine._execute_stack(private, Path(private["output"]))
    assert waited == [True]
    diagnostics = json.loads(
        (engine._directory(session["session_id"]) / "diagnostics.json").read_text()
    )
    assert diagnostics["exit_code"] == 0
    assert "Stack ready" in diagnostics["output"]
    assert diagnostics["progress_warning"]


def test_unexpected_worker_error_is_recorded_and_redacted(draft, monkeypatch):
    engine, session = draft
    plan = engine.plan(session["session_id"])
    job = engine.apply(
        session["session_id"], plan["plan_id"], plan["revision"], launch=False
    )

    def fail(*_):
        raise RuntimeError(f"failure involving {KEY} and {KEY.replace('-', '')}")

    engine.run_job(session["session_id"], job["job_id"], start_callback=fail)
    public = engine.get(session["session_id"])
    assert public["status"] == "FAILED"
    assert public["diagnostics"]["error_type"] == "RuntimeError"
    assert "<redacted>" in public["diagnostics"]["error"]
    assert KEY not in json.dumps(public)
    assert KEY.replace("-", "") not in json.dumps(public)


@pytest.mark.parametrize("code", ["SETUP_CHILD_ACTIVE", "SETUP_STACK_COMMITTED"])
def test_uncertain_runner_outcome_retains_candidate_files(draft, monkeypatch, code):
    engine, session = draft
    output = Path(session["output"])
    output.mkdir()
    (output / ".env").write_text("old configuration")
    plan = engine.plan(session["session_id"])
    job = engine.apply(
        session["session_id"], plan["plan_id"], plan["revision"], launch=False
    )

    def fail(*_):
        raise SetupError("runner outcome requires inspection", code)

    engine.run_job(session["session_id"], job["job_id"], start_callback=fail)
    public = engine.get(session["session_id"])
    assert public["status"] == "RECOVERY_REQUIRED"
    assert (output / ".env").read_text() != "old configuration"
    backup = engine._directory(session["session_id"]) / f"backup-{job['job_id']}"
    assert (backup / ".env").read_text() == "old configuration"


def test_stream_failure_waits_for_runner_before_returning(draft, monkeypatch):
    engine, session = draft
    private = engine._read(session["session_id"])
    private["plan"] = {
        "preflight": {"existing": [], "port_options": []},
        "_stage": private["output"],
    }
    private["job"] = {"job_id": "job"}
    monkeypatch.setattr(
        module, "_endpoints", lambda _: {"api": "http://127.0.0.1:8000"}
    )
    events = []

    class Stream:
        def __iter__(self):
            raise OSError("pipe read failed")

        def close(self):
            events.append("closed")

    class Process:
        pid = 123
        stdout = Stream()

        def wait(self, timeout=None):
            events.append("waited")
            raise subprocess.TimeoutExpired("runner", timeout)

    monkeypatch.setattr(module.subprocess, "Popen", lambda *a, **k: Process())
    with pytest.raises(SetupError) as error:
        engine._execute_stack(private, Path(private["output"]))
    assert error.value.code == "SETUP_CHILD_ACTIVE"
    assert events.index("closed") < events.index("waited")


@pytest.mark.skipif(os.name != "nt", reason="Native Windows stack runner")
def test_real_child_finishes_despite_progress_write_failure(draft, monkeypatch):
    engine, session = draft
    output = Path(session["output"])
    output.mkdir()
    (output / "stack_runner.py").write_text(
        "from pathlib import Path; import time\n"
        "print('Container creating',flush=True)\n"
        "time.sleep(.2)\n"
        "Path('completed.txt').write_text('done')\n"
        "print('Stack ready',flush=True)\n"
    )
    private = engine._read(session["session_id"])
    private["plan"] = {
        "preflight": {"existing": [], "port_options": []},
        "_stage": str(output),
    }
    private["job"] = {"job_id": "job"}
    monkeypatch.setattr(
        module, "_endpoints", lambda _: {"api": "http://127.0.0.1:8000"}
    )
    real_write = atomic_json

    def write(path, value):
        if path.name == "progress.json":
            raise PermissionError("held file")
        real_write(path, value)

    monkeypatch.setattr(module, "atomic_json", write)
    engine._execute_stack(private, output)
    assert (output / "completed.txt").read_text() == "done"
    assert engine.get(session["session_id"])["diagnostics"]["exit_code"] == 0
