# SPDX-License-Identifier: MIT
"""Arrow-key selection controls for interactive terminal prompts."""

from __future__ import annotations

import os
import select
import shutil
import sys
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence


@dataclass(frozen=True)
class SelectionResult:
    """A completed terminal selection, with 1-based option indexes."""

    indices: List[int]
    shortcut: Optional[str] = None


def is_interactive() -> bool:
    """Return whether raw-key selection is available on the current streams."""

    try:
        return bool(sys.stdin.isatty() and sys.stdout.isatty())
    except (AttributeError, OSError):
        return False


def select_many(
    prompt: str,
    options: Sequence[str],
    *,
    initial_indices: Iterable[int] = (),
    allow_empty: bool = False,
    select_all_key: Optional[str] = None,
    shortcut_keys: Sequence[str] = (),
    exclusive_indices: Iterable[int] = (),
) -> Optional[SelectionResult]:
    """Display a checkbox list; return ``None`` when stdin/stdout are not TTYs."""

    if not is_interactive():
        return None
    if not options:
        return SelectionResult([])

    selected = {index - 1 for index in initial_indices if 1 <= index <= len(options)}
    exclusive = {index - 1 for index in exclusive_indices if 1 <= index <= len(options)}
    cursor = 0
    status = ""
    rendered_lines = 0

    while True:
        lines = _many_lines(
            prompt,
            options,
            selected,
            exclusive,
            cursor,
            select_all_key=select_all_key,
            shortcut_keys=shortcut_keys,
            status=status,
        )
        rendered_lines = _render(lines, rendered_lines)
        status = ""
        key = _read_key()

        if key == "up":
            cursor = (cursor - 1) % len(options)
        elif key == "down":
            cursor = (cursor + 1) % len(options)
        elif key == "space":
            if cursor in selected:
                selected.remove(cursor)
            else:
                if cursor in exclusive:
                    selected.clear()
                else:
                    selected.difference_update(exclusive)
                selected.add(cursor)
        elif key == "enter":
            if cursor in exclusive:
                return SelectionResult([cursor + 1])
            if selected or allow_empty:
                return SelectionResult(sorted(index + 1 for index in selected))
            status = "Select at least one option before continuing."
        elif key in {"q", "quit"}:
            return SelectionResult([], shortcut="q")
        elif select_all_key and key == select_all_key.lower():
            selected = set(range(len(options)))
        elif key in shortcut_keys:
            return SelectionResult([], shortcut=key)


def select_one(
    prompt: str,
    options: Sequence[str],
) -> Optional[SelectionResult]:
    """Display a single-choice list; return ``None`` when streams are not TTYs."""

    if not is_interactive():
        return None
    if not options:
        return SelectionResult([])

    cursor = 0
    rendered_lines = 0
    while True:
        lines = _one_lines(prompt, options, cursor)
        rendered_lines = _render(lines, rendered_lines)
        key = _read_key()

        if key == "up":
            cursor = (cursor - 1) % len(options)
        elif key == "down":
            cursor = (cursor + 1) % len(options)
        elif key == "enter":
            return SelectionResult([cursor + 1])
        elif key in {"q", "quit"}:
            return SelectionResult([], shortcut="q")


def _many_lines(
    prompt: str,
    options: Sequence[str],
    selected: set[int],
    exclusive: set[int],
    cursor: int,
    *,
    select_all_key: Optional[str],
    shortcut_keys: Sequence[str],
    status: str,
) -> List[str]:
    width = max(40, shutil.get_terminal_size((80, 20)).columns)
    lines = [_fit(prompt, width)]
    for index, option in enumerate(options):
        pointer = ">" if index == cursor else " "
        checkbox = "x" if index in selected else " "
        label_width = max(8, width - 9)
        label = _fit(f"{index + 1}. {option}", label_width)
        marker = checkbox if index in selected else ("→" if index in exclusive else " ")
        lines.append(f"{pointer} [{marker}] {label}")

    hints = ["↑/↓ move", "Space toggle", "Enter confirm", "q quit"]
    if select_all_key:
        hints.append(f"{select_all_key} all")
    if shortcut_keys:
        hints.append("/".join(shortcut_keys) + " special choice")
    lines.append(_fit("  " + "  •  ".join(hints), width))
    if status:
        lines.append(_fit("  " + status, width))
    return lines


def _one_lines(prompt: str, options: Sequence[str], cursor: int) -> List[str]:
    width = max(40, shutil.get_terminal_size((80, 20)).columns)
    lines = [_fit(prompt, width)]
    for index, option in enumerate(options):
        pointer = ">" if index == cursor else " "
        label = _fit(f"{index + 1}. {option}", max(8, width - 5))
        lines.append(f"{pointer} {label}")
    lines.append(_fit("  ↑/↓ move  •  Enter confirm  •  q quit", width))
    return lines


def _fit(value: str, width: int) -> str:
    """Keep one terminal row from wrapping during cursor-based redraws."""

    clean = " ".join(str(value).split())
    if len(clean) <= width:
        return clean
    if width < 2:
        return clean[:width]
    return clean[: width - 1] + "…"


def _render(lines: Sequence[str], previous_line_count: int) -> int:
    if previous_line_count:
        sys.stdout.write(f"\x1b[{previous_line_count}A")
    for line in lines:
        sys.stdout.write("\r\x1b[2K" + line + "\n")
    sys.stdout.flush()
    return len(lines)


def _read_key() -> str:
    if os.name == "nt":
        import msvcrt

        char = msvcrt.getwch()
        if char in {"\x00", "\xe0"}:
            return {"H": "up", "P": "down"}.get(msvcrt.getwch(), "")
        if char == "\x03":
            raise KeyboardInterrupt
        return {
            "\r": "enter",
            "\n": "enter",
            " ": "space",
            "\x1b": "escape",
        }.get(char, char.lower())

    import termios
    import tty

    stream = sys.stdin
    fd = stream.fileno()
    previous = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        char = os.read(fd, 1).decode("utf-8", errors="ignore")
        if char == "\x03":
            raise KeyboardInterrupt
        if char == "\x1b":
            if not select.select([fd], [], [], 0.08)[0]:
                return "escape"
            sequence = os.read(fd, 1).decode("utf-8", errors="ignore")
            if sequence == "[" and select.select([fd], [], [], 0.08)[0]:
                sequence += os.read(fd, 1).decode("utf-8", errors="ignore")
            return {"[A": "up", "[B": "down", "[H": "up", "[F": "down"}.get(
                sequence, "escape"
            )
        return {
            "\r": "enter",
            "\n": "enter",
            " ": "space",
        }.get(char, char.lower())
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, previous)
