# SPDX-License-Identifier: MIT
"""Hidden product-key input with Windows console paste support."""

from __future__ import annotations

import getpass
import os
import sys


def _is_windows_console() -> bool:
    return os.name == "nt" and sys.stdin is sys.__stdin__ and sys.stdin.isatty()


def _clipboard_text() -> str | None:
    """Copy Unicode text only on an explicit Ctrl+V; leave the clipboard intact."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.CloseClipboard.argtypes = []
    user32.CloseClipboard.restype = wintypes.BOOL
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = wintypes.HANDLE
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.restype = wintypes.BOOL
    kernel32.GlobalSize.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalSize.restype = ctypes.c_size_t
    if not user32.OpenClipboard(None):
        return None
    try:
        handle = user32.GetClipboardData(13)  # CF_UNICODETEXT
        if not handle:
            return None
        size = kernel32.GlobalSize(handle)
        # Clipboard contents are untrusted. Bound the read and do not assume
        # a NUL terminator or a reasonable amount of text for a product key.
        if size == 0 or size > 8192 or size % ctypes.sizeof(ctypes.c_wchar):
            return None
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            return None
        try:
            text = ctypes.wstring_at(pointer, size // ctypes.sizeof(ctypes.c_wchar))
            return text.split("\x00", 1)[0].strip()
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def read_secret(prompt: str) -> str:
    if not _is_windows_console():
        return getpass.getpass(prompt)

    import msvcrt

    def write(text: str) -> None:
        for char in text:
            msvcrt.putwch(char)

    write(prompt)
    value = ""
    while True:
        char = msvcrt.getwch()
        if char in {"\r", "\n"}:
            write("\r\n")
            return value
        if char == "\x03":
            raise KeyboardInterrupt
        if char in {"", "\x1a"}:
            raise EOFError
        if char in {"\x00", "\xe0"}:
            msvcrt.getwch()  # Consume extended keys; do not append their codes.
            continue
        if char == "\b":
            if value:
                value = value[:-1]
                write("\b \b")
            continue
        if char == "\x16":
            try:
                pasted = _clipboard_text()
            except OSError:
                pasted = None
            if pasted is None:
                write("\r\nClipboard unavailable. Try again or use the terminal paste menu.\r\n")
                write(prompt + "*" * len(value))
                continue
            value += pasted
            write("*" * len(pasted))
        elif char.isprintable():
            value += char
            write("*")
