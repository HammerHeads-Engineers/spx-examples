# SPDX-License-Identifier: MIT
"""Windows hidden input must handle paste without echoing the product key."""

import getpass
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from installer import secret_input

TEST_KEY = "AAAAA-AAAAA-AAAAA-AAAAA-AAAAA-AAAAA"


def test_windows_ctrl_v_reads_clipboard_without_echo(monkeypatch):
    keys = iter(["\x16", "\r"])
    output = []
    console = SimpleNamespace(getwch=lambda: next(keys), putwch=output.append)
    monkeypatch.setitem(sys.modules, "msvcrt", console)
    monkeypatch.setattr(getpass, "msvcrt", console, raising=False)
    monkeypatch.setattr(sys, "stdin", sys.__stdin__)
    monkeypatch.setattr(secret_input, "_is_windows_console", lambda: True)
    monkeypatch.setattr(secret_input, "_clipboard_text", lambda: TEST_KEY, raising=False)
    assert secret_input.read_secret("Key: ") == TEST_KEY
    assert TEST_KEY not in "".join(output)


def _console(monkeypatch, sequence):
    keys = iter(sequence)
    output = []
    monkeypatch.setitem(sys.modules, "msvcrt", SimpleNamespace(
        getwch=lambda: next(keys), putwch=output.append
    ))
    monkeypatch.setattr(secret_input, "_is_windows_console", lambda: True)
    return output


def test_typing_terminal_managed_paste_and_editing(monkeypatch):
    output = _console(monkeypatch, ["\xe0", "K", "\x00", "H", "\x01", *TEST_KEY, "X", "\b", "\n"])
    assert secret_input.read_secret("Key: ") == TEST_KEY
    assert TEST_KEY not in "".join(output)


@pytest.mark.parametrize("char,error", [("\x03", KeyboardInterrupt), ("\x1a", EOFError)])
def test_windows_cancel_and_eof(monkeypatch, char, error):
    _console(monkeypatch, [char])
    with pytest.raises(error):
        secret_input.read_secret("Key: ")


def test_unavailable_clipboard_allows_retry_without_losing_typed_value(monkeypatch):
    output = _console(monkeypatch, ["A", "\x16", "\x16", "\r"])
    monkeypatch.setattr(secret_input, "_clipboard_text", Mock(side_effect=[OSError("busy"), TEST_KEY[1:]]))
    assert secret_input.read_secret("Key: ") == TEST_KEY
    assert "Clipboard unavailable" in "".join(output)
    assert TEST_KEY not in "".join(output)


def test_non_windows_or_redirected_input_keeps_getpass(monkeypatch):
    monkeypatch.setattr(secret_input, "_is_windows_console", lambda: False)
    prompt = Mock(return_value=TEST_KEY)
    monkeypatch.setattr(getpass, "getpass", prompt)
    assert secret_input.read_secret("Key: ") == TEST_KEY
    prompt.assert_called_once_with("Key: ")


def test_wizard_accepts_ctrl_v_and_retains_strict_validation(monkeypatch, capsys):
    from installer.wizard import InstallerWizard
    monkeypatch.delenv("SPX_PRODUCT_KEY", raising=False)
    output = _console(monkeypatch, ["\x16", "\r", "\x16", "\r"])
    monkeypatch.setattr(secret_input, "_clipboard_text", Mock(side_effect=["invalid", TEST_KEY]))
    assert InstallerWizard()._prompt_license_key() == TEST_KEY
    assert "Invalid SPX product key format" in capsys.readouterr().out
    assert TEST_KEY not in "".join(output)


@pytest.mark.parametrize("failure", [None, "open", "handle", "size", "lock", "read"])
def test_clipboard_bounds_and_cleanup(monkeypatch, failure):
    import ctypes
    buffer = ctypes.create_unicode_buffer(TEST_KEY)
    user32 = SimpleNamespace(
        OpenClipboard=Mock(return_value=failure != "open"),
        CloseClipboard=Mock(),
        GetClipboardData=Mock(return_value=0 if failure == "handle" else 123),
    )
    kernel32 = SimpleNamespace(
        GlobalSize=Mock(return_value=10000 if failure == "size" else ctypes.sizeof(buffer)),
        GlobalLock=Mock(return_value=0 if failure == "lock" else ctypes.addressof(buffer)),
        GlobalUnlock=Mock(),
    )
    monkeypatch.setattr(ctypes, "WinDLL", lambda name, **kwargs: user32 if name == "user32" else kernel32, raising=False)
    if failure == "read":
        monkeypatch.setattr(ctypes, "wstring_at", Mock(side_effect=OSError("read failed")))
        with pytest.raises(OSError):
            secret_input._clipboard_text()
    else:
        assert secret_input._clipboard_text() == (TEST_KEY if failure is None else None)
    assert user32.CloseClipboard.call_count == int(failure != "open")
    assert kernel32.GlobalUnlock.call_count == int(failure in {None, "read"})
