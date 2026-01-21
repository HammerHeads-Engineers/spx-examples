# SPDX-License-Identifier: MIT
"""Small console styling helpers shared by the installer."""

from __future__ import annotations

from shutil import get_terminal_size

try:
    from colorama import Fore, Style, init as colorama_init
except Exception:  # pragma: no cover - colorama optional fallback
    Fore = Style = None  # type: ignore
    colorama_init = None  # type: ignore

if colorama_init is not None:
    colorama_init(autoreset=True)


def style(text: str, *, fg: str | None = None, bold: bool = False) -> str:
    """Apply ANSI styles if available."""
    if Fore is None or Style is None:
        return text
    parts = []
    if bold:
        parts.append(Style.BRIGHT)
    if fg:
        parts.append(fg)
    parts.append(text)
    if parts:
        parts.append(Style.RESET_ALL)
    return "".join(parts)


def heading(text: str) -> str:
    return style(text, fg=Fore.GREEN if Fore else None, bold=True)


def accent(text: str) -> str:
    return style(text, fg=Fore.CYAN if Fore else None, bold=True)


def success(text: str) -> str:
    return style(text, fg=Fore.GREEN if Fore else None, bold=True)


def warn(text: str) -> str:
    return style(text, fg=Fore.YELLOW if Fore else None, bold=True)


def error(text: str) -> str:
    return style(text, fg=Fore.RED if Fore else None, bold=True)


def hr(char: str = "=", width: int | None = None) -> str:
    width = width or max(60, min(get_terminal_size((80, 20)).columns, 120))
    return char * width
