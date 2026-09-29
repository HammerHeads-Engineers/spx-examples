# SPDX-License-Identifier: MIT
"""Tests for interactive terminal selection behavior."""

from installer import terminal_selection


def test_select_many_uses_arrows_and_space_to_toggle(monkeypatch) -> None:
    keys = iter(["down", "space", "enter"])
    monkeypatch.setattr(terminal_selection, "is_interactive", lambda: True)
    monkeypatch.setattr(terminal_selection, "_read_key", lambda: next(keys))

    result = terminal_selection.select_many("Select:", ["first", "second"])

    assert result is not None
    assert result.indices == [2]


def test_select_many_can_change_default_selection(monkeypatch) -> None:
    keys = iter(["space", "enter"])
    monkeypatch.setattr(terminal_selection, "is_interactive", lambda: True)
    monkeypatch.setattr(terminal_selection, "_read_key", lambda: next(keys))

    result = terminal_selection.select_many(
        "Select:",
        ["first", "second"],
        initial_indices=[1, 2],
    )

    assert result is not None
    assert result.indices == [2]


def test_select_many_enters_exclusive_choice(monkeypatch) -> None:
    keys = iter(["down", "enter"])
    monkeypatch.setattr(terminal_selection, "is_interactive", lambda: True)
    monkeypatch.setattr(terminal_selection, "_read_key", lambda: next(keys))

    result = terminal_selection.select_many(
        "Select:",
        ["package", "choose protocols"],
        exclusive_indices=[2],
    )

    assert result is not None
    assert result.indices == [2]


def test_select_one_uses_arrow_navigation(monkeypatch) -> None:
    keys = iter(["down", "enter"])
    monkeypatch.setattr(terminal_selection, "is_interactive", lambda: True)
    monkeypatch.setattr(terminal_selection, "_read_key", lambda: next(keys))

    result = terminal_selection.select_one("Select:", ["first", "second"])

    assert result is not None
    assert result.indices == [2]


def test_select_many_falls_back_without_a_terminal(monkeypatch) -> None:
    monkeypatch.setattr(terminal_selection, "is_interactive", lambda: False)

    assert terminal_selection.select_many("Select:", ["first"]) is None
