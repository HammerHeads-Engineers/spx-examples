# SPDX-License-Identifier: MIT
"""Tests for installer.runtime_bootstrap."""

from __future__ import annotations

import json
from pathlib import Path

from installer import runtime_bootstrap


def test_is_healthy_virtualenv_rejects_missing_pyvenv_cfg(tmp_path: Path) -> None:
    venv_dir = tmp_path / ".venv"
    (venv_dir / "bin").mkdir(parents=True)
    (venv_dir / "bin" / "python").write_text("", encoding="utf-8")

    assert runtime_bootstrap.is_healthy_virtualenv(venv_dir) is False


def test_ensure_runtime_recreates_broken_virtualenv(tmp_path: Path, monkeypatch) -> None:
    venv_dir = tmp_path / ".venv"
    python_path = runtime_bootstrap.venv_python_path(venv_dir)
    python_path.parent.mkdir(parents=True)
    python_path.write_text("", encoding="utf-8")
    stale_path = venv_dir / "stale.txt"
    stale_path.write_text("stale", encoding="utf-8")

    calls: list[list[str]] = []

    def fake_run_command(argv: list[str]) -> None:
        calls.append(argv)
        assert argv == [runtime_bootstrap.sys.executable, "-m", "venv", str(venv_dir)]
        python_path.parent.mkdir(parents=True, exist_ok=True)
        python_path.write_text("#!/usr/bin/env python\n", encoding="utf-8")
        (venv_dir / "pyvenv.cfg").write_text("home = /tmp/python\n", encoding="utf-8")

    monkeypatch.setattr(runtime_bootstrap, "run_command", fake_run_command)
    monkeypatch.setattr(
        runtime_bootstrap,
        "is_healthy_virtualenv",
        lambda candidate: (candidate / "pyvenv.cfg").exists(),
    )

    python_bin = runtime_bootstrap.ensure_runtime(venv_dir, [])

    assert calls == [[runtime_bootstrap.sys.executable, "-m", "venv", str(venv_dir)]]
    assert python_bin == python_path
    assert stale_path.exists() is False
    assert (venv_dir / "pyvenv.cfg").exists() is True
    assert json.loads((venv_dir / ".spx-runtime.json").read_text(encoding="utf-8")) == {
        "packages": [],
        "python_version": runtime_bootstrap.sys.version,
    }


def test_ensure_runtime_reuses_healthy_virtualenv_without_recreate(
    tmp_path: Path,
    monkeypatch,
) -> None:
    venv_dir = tmp_path / ".venv"
    python_path = runtime_bootstrap.venv_python_path(venv_dir)
    python_path.parent.mkdir(parents=True)
    python_path.write_text("#!/usr/bin/env python\n", encoding="utf-8")
    (venv_dir / "pyvenv.cfg").write_text("home = /tmp/python\n", encoding="utf-8")
    (venv_dir / ".spx-runtime.json").write_text(
        json.dumps(
            {
                "packages": [],
                "python_version": runtime_bootstrap.sys.version,
            }
        ),
        encoding="utf-8",
    )

    calls: list[list[str]] = []

    monkeypatch.setattr(runtime_bootstrap, "run_command", lambda argv: calls.append(argv))
    monkeypatch.setattr(runtime_bootstrap, "is_healthy_virtualenv", lambda candidate: True)

    python_bin = runtime_bootstrap.ensure_runtime(venv_dir, [])

    assert python_bin == python_path
    assert calls == []
