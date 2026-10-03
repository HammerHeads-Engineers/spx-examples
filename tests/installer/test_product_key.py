# SPDX-License-Identifier: MIT
"""Reject malformed keys before Setup can replace a working Docker stack."""

import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock

import pytest

from installer import product_key as pk
from installer import stack_manager as sm
from installer import stack_runner as sr
from installer.wizard import InstallerWizard


TEST_KEY = "AAAAA-AAAAA-AAAAA-AAAAA-AAAAA-AAAAA"


@pytest.mark.parametrize("value", [TEST_KEY, "A" * 30])
def test_accepts_only_supported_key_shapes(value):
    assert pk.validate_product_key_format(value) == value


@pytest.mark.parametrize(
    "value",
    [
        "",
        "y",
        "REPLACE_ME",
        "A" * 29,
        "A" * 31,
        "a" * 30,
        "  " + TEST_KEY + "  ",
        "A" * 29 + "0",
        "A" * 29 + "1",
        "A" * 29 + "8",
        "A" * 29 + "9",
        "A" * 29 + "!",
        "A" * 15 + " " + "A" * 15,
        "А" * 30,
        "AAAA-AA-AAAA-AAAA-AAAA-AAAA-AAAA-AAAA",
    ],
)
def test_rejects_bad_length_alphabet_and_grouping_without_echoing(value):
    with pytest.raises(ValueError, match="30 uppercase characters") as error:
        pk.validate_product_key_format(value)
    assert str(error.value) == pk.FORMAT_GUIDANCE


@pytest.mark.parametrize(
    "raw",
    [TEST_KEY, f"'{TEST_KEY}'", f'"{TEST_KEY}" # comment', f"{TEST_KEY} # comment"],
)
def test_dotenv_key_parsing(tmp_path, monkeypatch, raw):
    monkeypatch.delenv("SPX_PRODUCT_KEY", raising=False)
    env = tmp_path / ".env"
    env.write_text(f"SPX_PRODUCT_KEY={raw}\n", encoding="utf-8")
    assert pk.runtime_product_key(env) == TEST_KEY


@pytest.mark.parametrize("value", ["y", ""])
def test_inherited_invalid_key_overrides_dotenv_and_is_rejected(
    tmp_path, monkeypatch, value
):
    env = tmp_path / ".env"
    env.write_text(f"SPX_PRODUCT_KEY={TEST_KEY}\n", encoding="utf-8")
    monkeypatch.setenv("SPX_PRODUCT_KEY", value)
    with pytest.raises(ValueError):
        pk.validate_product_key_format(pk.runtime_product_key(env))


def test_dotenv_last_key_wins_like_compose(tmp_path, monkeypatch):
    monkeypatch.delenv("SPX_PRODUCT_KEY", raising=False)
    env = tmp_path / ".env"
    env.write_text(f"SPX_PRODUCT_KEY=y\nSPX_PRODUCT_KEY={TEST_KEY}\n", encoding="utf-8")
    assert pk.runtime_product_key(env) == TEST_KEY


def test_dotenv_hash_without_space_is_not_silently_ignored(tmp_path, monkeypatch):
    monkeypatch.delenv("SPX_PRODUCT_KEY", raising=False)
    env = tmp_path / ".env"
    env.write_text(f"SPX_PRODUCT_KEY={TEST_KEY}#invalid\n", encoding="utf-8")
    with pytest.raises(ValueError):
        pk.validate_product_key_format(pk.runtime_product_key(env))


def test_wizard_reprompts_for_partial_paste_without_echoing(monkeypatch, capsys):
    monkeypatch.delenv("SPX_PRODUCT_KEY", raising=False)
    inputs = iter(["y", "PRIVATE-invalid-input", "  " + TEST_KEY + "  "])
    prompt = Mock(side_effect=lambda _: next(inputs))
    monkeypatch.setattr("getpass.getpass", prompt)
    assert InstallerWizard()._prompt_license_key() == TEST_KEY
    assert prompt.call_count == 3
    output = capsys.readouterr().out
    assert "30 uppercase characters" in output
    assert "PRIVATE-invalid-input" not in output and TEST_KEY not in output


def test_wizard_recovers_from_invalid_inherited_key(monkeypatch, capsys):
    monkeypatch.setenv("SPX_PRODUCT_KEY", "PRIVATE-invalid-env")
    monkeypatch.setattr("getpass.getpass", Mock(return_value=TEST_KEY))
    assert InstallerWizard()._prompt_license_key() == TEST_KEY
    output = capsys.readouterr().out
    assert "environment is invalid" in output and "PRIVATE-invalid-env" not in output


def test_prepare_rejects_invalid_key_before_docker_or_snapshot_changes(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("SPX_PRODUCT_KEY", raising=False)
    env = tmp_path / ".env"
    env.write_text("SPX_PRODUCT_KEY=y\n", encoding="utf-8")
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text("previous snapshot")
    runner = Mock(side_effect=AssertionError("Docker must not be called"))
    manager = sm.StackManager(tmp_path / "compose.yml", env, runner=runner)
    with pytest.raises(sm.PreflightError, match="30 uppercase characters"):
        manager.prepare(snapshot, assume_yes=True)
    runner.assert_not_called()
    assert snapshot.read_text() == "previous snapshot"


def test_generated_validator_returns_nonzero_without_echoing_key(tmp_path):
    env = tmp_path / ".env"
    env.write_text("SPX_PRODUCT_KEY=PRIVATE-invalid-input\n", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(Path(pk.__file__)), "--env-file", str(env)],
        env={
            key: value for key, value in os.environ.items() if key != "SPX_PRODUCT_KEY"
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "30 uppercase characters" in result.stderr
    assert "PRIVATE-invalid-input" not in result.stdout + result.stderr


def test_windows_start_stops_before_runtime_preflight_and_rollback(
    tmp_path, monkeypatch, capsys
):
    for name in (
        "stack_manager.py",
        "docker-compose.generated.yml",
        ".env",
        "bundle.json",
        "docker-compose.transaction.yml",
        "network.py",
        "modbus_port_configurator.py",
        "runtime_bootstrap.py",
        "bootstrap_runner.py",
        "product_key.py",
    ):
        (tmp_path / name).write_text("unused", encoding="utf-8")
    (tmp_path / "bundle.json").write_text('{"installation_id":"install"}')
    monkeypatch.setattr(sr.shutil, "which", lambda name: name)
    calls = []

    def fail_validation(args, **kwargs):
        calls.append(args)
        raise sr.StartFailure("product-key", pk.FORMAT_GUIDANCE)

    monkeypatch.setattr(sr, "_run", fail_validation)
    monkeypatch.setattr(
        sr.subprocess, "run", Mock(side_effect=AssertionError("Runtime must not start"))
    )
    assert sr._start(tmp_path, assume_yes=True) == 1
    assert len(calls) == 1 and Path(calls[0][1]).name == "product_key.py"
    output = capsys.readouterr().err
    assert "stage=product-key" in output and "attempting rollback" not in output
